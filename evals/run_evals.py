"""Retrieval + agent evals. `--gate` exits non-zero if any metric is below evals/thresholds.json,
which is what blocks a bad change in CI."""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engintel import config                                   # noqa: E402
from engintel.agents.graph import ask                         # noqa: E402
from engintel.retrieval.hybrid import retrieve                # noqa: E402

HERE = Path(__file__).resolve().parent
ID_RE = re.compile(r"\b(?:REQ|TC|RES|FAIL|CR)-\d+\b")

def is_relevant(chunk, rel):
    return any(chunk["source"] == r["source"] and chunk["section"].split()[0] == r["section_num"] for r in rel)

def retrieval_eval(modes):
    qs = json.loads((HERE / "retrieval_questions.json").read_text())
    table = {}
    for mode, rerank in modes:
        recall, rr, t0 = 0, 0.0, time.perf_counter()
        for item in qs:
            hits = retrieve(item["q"], k=10, mode=mode, rerank=rerank)
            ranks = [i for i, h in enumerate(hits, 1) if is_relevant(h, item["relevant"])]
            recall += bool(ranks and ranks[0] <= 5)
            rr += 1 / ranks[0] if ranks else 0
        name = mode + (" + rerank" if rerank else "")
        table[name] = {"recall@5": round(recall / len(qs), 3), "mrr": round(rr / len(qs), 3),
                       "ms_per_query": round((time.perf_counter() - t0) * 1000 / len(qs), 1)}
    return table, len(qs)

def agent_eval():
    cases = json.loads((HERE / "agent_cases.json").read_text())
    rows = []
    for c in cases:
        st = ask(c["q"])
        ans = st["answer"]
        ids = set(ID_RE.findall(ans))
        cited_refs = [e["ref"] for e in st.get("evidence", []) if e["eid"] in set(st.get("citations", []))]
        fails = []
        if st.get("answerable") != c["answerable"]:
            fails.append(f"answerable={st.get('answerable')} expected {c['answerable']}")
        if missing := set(c.get("expect_ids", [])) - ids:
            fails.append(f"missing ids {sorted(missing)}")
        if extra := set(c.get("forbid_ids", [])) & ids:
            fails.append(f"forbidden ids {sorted(extra)}")
        for s in c.get("expect_contains", []):
            if s.lower() not in ans.lower():
                fails.append(f"missing text '{s}'")
        if c.get("expect_source") and not any(c["expect_source"] in r for r in cited_refs):
            fails.append(f"did not cite {c['expect_source']}")
        if not st["validation"]["passed"]:
            fails.append(f"validation: {st['validation']['issues']}")
        rows.append({"category": c["category"], "q": c["q"], "passed": not fails, "fails": fails})
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--rerank", action="store_true", help="also evaluate cross-encoder rerank")
    a = ap.parse_args()
    modes = [("dense", False), ("bm25", False), ("hybrid", False)] + ([("hybrid", True)] if a.rerank else [])
    rt, n = retrieval_eval(modes)
    print(f"\nRetrieval ({n} questions, embedder={config.EMBEDDER})")
    print("| mode | recall@5 | MRR | ms/query |\n|---|---|---|---|")
    for m, r in rt.items():
        print(f"| {m} | {r['recall@5']} | {r['mrr']} | {r['ms_per_query']} |")
    rows = agent_eval()
    rate = sum(r["passed"] for r in rows) / len(rows)
    print(f"\nAgent ({len(rows)} cases, llm={'on' if config.USE_LLM else 'off'}): pass rate {rate:.2f}")
    cats = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r["passed"])
    for k, v in cats.items():
        print(f"  {k:<14} {sum(v)}/{len(v)}")
    for r in rows:
        if not r["passed"]:
            print(f"  FAIL: {r['q']} -> {r['fails']}")
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / "latest.json").write_text(json.dumps({"retrieval": rt, "agent_pass_rate": rate, "agent": rows}, indent=1))
    if a.gate:
        th = json.loads((HERE / "thresholds.json").read_text())
        got = {"retrieval_hybrid_recall@5": rt["hybrid"]["recall@5"], "retrieval_hybrid_mrr": rt["hybrid"]["mrr"],
               "agent_pass_rate": rate}
        bad = {k: (got[k], v) for k, v in th.items() if not k.startswith("_") and got[k] < v}
        if bad:
            print(f"\nGATE FAILED: {bad}"); sys.exit(1)
        print("\nGATE PASSED")

if __name__ == "__main__":
    main()
