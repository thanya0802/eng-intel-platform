"""Agent nodes. Each takes the state dict and returns a partial update.

planner -> retrieval -> sql -> traceability -> report -> validate
Tool nodes no-op when the planner didn't select them. Every node has a deterministic
path; Gemini is used for planning/SQL/answers only when GEMINI_API_KEY is set.
"""
import re
from .. import llm, store, trace
from ..retrieval.hybrid import retrieve
from ..retrieval.text import tokenize
from ..sql_guard import UnsafeSQL, guard
from ..telemetry import span

ID_RE = re.compile(r"\b(?:REQ|TC|RES|FAIL|CR)-\d+\b")
TRACE_WORDS = ("trace", "traceab", "linked", "chain", "failing test", "change request", "root cause")
SQL_RE = re.compile(r"\b(how many|count|number of|list (?:all|the)|which requirements are)\b")
NO_EVIDENCE = "I don't have evidence in the indexed documents or records to answer that."
MIN_COVERAGE = 0.5   # share of query terms the best chunk must contain to count as evidence

def _add_evidence(state, kind, ref, text, **extra):
    ev = state.setdefault("evidence", [])
    eid = f"E{len(ev) + 1}"
    ev.append({"eid": eid, "kind": kind, "ref": ref, "text": text, **extra})
    return eid

# ---------------- planner ----------------
def planner(state):
    q, ql = state["question"], state["question"].lower()
    with span("planner", state["run_id"]):
        ids = ID_RE.findall(q)
        if llm.available():
            try:
                p = llm.generate_json(PLANNER_PROMPT.format(q=q), state["run_id"], "planner")
                tools = [t for t in p.get("tools", []) if t in ("retrieval", "sql", "traceability")]
                if tools:
                    return {"plan": {"tools": tools, "ids": ids, "by": "llm"}}
            except Exception:
                pass  # fall back to rules
        tools = []
        if ids or any(w in ql for w in TRACE_WORDS):
            tools.append("traceability")
        if SQL_RE.search(ql):
            tools.append("sql")
        if not tools or ids or "traceability" in tools and not SQL_RE.search(ql):
            tools.insert(0, "retrieval")
        return {"plan": {"tools": tools, "ids": ids, "by": "rules"}}

PLANNER_PROMPT = """You route engineering questions to tools. Tools:
- retrieval: search engineering PDFs (specs, test reports, procedures, review minutes)
- sql: aggregate/list queries over tables requirements, test_cases, test_results, failure_logs, change_requests
- traceability: follow links requirement -> test -> result -> failure -> change request
Question: {q}
Return JSON: {{"tools": [...]}}"""

# ---------------- retrieval ----------------
def retrieval_node(state):
    if "retrieval" not in state["plan"]["tools"]:
        return {}
    with span("retrieval", state["run_id"]):
        hits = retrieve(state["question"], k=5)
    upd = {"evidence": list(state.get("evidence", [])), "hits": hits}
    tmp = {"evidence": upd["evidence"]}
    q_ids = set(state["plan"]["ids"])
    llm_mode = llm.available()
    for h in hits:
        # Extractive mode: admit a chunk only if it covers enough query terms or mentions an ID the
        # user asked about (weak matches make bad extracted sentences). LLM mode: pass all top hits;
        # the model can recognise an answer that shares no words with the question ("fretting
        # corrosion" for "what caused the failures"), but only if it is allowed to see it.
        if llm_mode or h["term_coverage"] >= MIN_COVERAGE * 0.6 or q_ids & set(ID_RE.findall(h["text"])):
            _add_evidence(tmp, "chunk", f"{h['source']} p.{h['page']} §{h['section']}", h["text"],
                          coverage=h["term_coverage"])
    return upd

# ---------------- sql ----------------
SQL_TEMPLATES = [
    (re.compile(r"how many requirements"), "SELECT status, COUNT(*) AS n FROM requirements GROUP BY status", ()),
    (re.compile(r"how many (?:failed|failing) tests?"),
     "SELECT COUNT(DISTINCT tc_id) AS failing_tests FROM test_results WHERE outcome='fail'", ()),
    (re.compile(r"(open|closed) change requests"), "SELECT cr_id, title, status FROM change_requests WHERE status=? ORDER BY cr_id", None),
    (re.compile(r"(high|medium|low) priority requirements"),
     "SELECT req_id, title, subsystem FROM requirements WHERE priority=? ORDER BY req_id", None),
    (re.compile(r"requirements (?:in|for) the (\w+) subsystem"),
     "SELECT req_id, title, priority FROM requirements WHERE subsystem=? ORDER BY req_id", None),
]
SCHEMA_HINT = """requirements(req_id, title, subsystem, priority, status)
test_cases(tc_id, req_id, title)
test_results(result_id, tc_id, outcome['pass'|'fail'], run_date)
failure_logs(fail_id, result_id, tc_id, description, severity, logged_at)
change_requests(cr_id, fail_id, title, status['open'|'closed'], opened_at)"""

def sql_node(state):
    if "sql" not in state["plan"]["tools"]:
        return {}
    ql = state["question"].lower()
    sql, params = None, ()
    for pat, tmpl, fixed in SQL_TEMPLATES:
        m = pat.search(ql)
        if m:
            sql, params = tmpl, fixed if fixed is not None else (m.group(1),)
            break
    if sql is None and llm.available():
        try:
            out = llm.generate_json(f"SQLite schema:\n{SCHEMA_HINT}\nWrite one read-only SELECT answering: "
                                    f"{state['question']}\nReturn JSON {{\"sql\": \"...\"}}", state["run_id"], "sql")
            sql = out["sql"]
        except Exception:
            sql = None
    if sql is None:
        return {"sql": {"query": None, "rows": [], "error": "no template matched and no LLM configured"}}
    try:
        safe = guard(sql)
        with span("sql", state["run_id"]):
            rows = store.query(safe, params)            # read-only connection
    except (UnsafeSQL, Exception) as e:
        return {"sql": {"query": sql, "rows": [], "error": f"{type(e).__name__}: {e}"}}
    tmp = {"evidence": list(state.get("evidence", []))}
    if rows:
        _add_evidence(tmp, "sql", "warehouse query", "; ".join(str(r) for r in rows[:25]))
    return {"sql": {"query": safe, "rows": rows}, "evidence": tmp["evidence"]}

# ---------------- traceability ----------------
def traceability_node(state):
    if "traceability" not in state["plan"]["tools"]:
        return {}
    ql = state["question"].lower()
    tmp = {"evidence": list(state.get("evidence", []))}
    out = {"chains": [], "edges": []}
    with span("traceability", state["run_id"]):
        ids = [i for i in state["plan"]["ids"] if trace.entity_exists(i)]
        if ids:
            for i in ids:
                edges = trace.trace(i)
                out["edges"] += edges
                if edges:
                    _add_evidence(tmp, "trace", i, "; ".join(f"{e['src']} -{e['rel']}-> {e['dst']}" for e in edges))
        else:
            status = "open" if "open" in ql else "closed" if "closed" in ql else "any"
            chains = trace.failing_chains(status)
            out["chains"] = chains
            for c in chains:
                _add_evidence(tmp, "trace", c["req_id"],
                    f"{c['req_id']} -> {c['tc_id']} -> {c['result_id']} (fail, {c['run_date']}) -> "
                    f"{c['fail_id']} ({c['severity']}) -> {c['cr_id']} ({c['cr_status']}): {c['change_request']}")
    return {"trace": out, "evidence": tmp["evidence"]}

# ---------------- report ----------------
def _best_sentence(text, q_terms):
    body = re.sub(r"^\[[^\]]*\]\s*", "", text)
    sents = [s.strip() for s in re.split(r"(?<=[.;])\s+", body) if len(s.split()) > 3]
    return max(sents, key=lambda s: len(q_terms & set(tokenize(s))), default=body[:300])

def extractive_answer(state):
    ev = state.get("evidence", [])
    q_terms = set(tokenize(state["question"]))
    parts, cited = [], []
    trace_ev = [e for e in ev if e["kind"] == "trace"]
    if trace_ev:
        parts.append(f"Traceability ({len(trace_ev)} item(s)):")
        for e in trace_ev[:10]:
            parts.append(f"- {e['text']} [{e['eid']}]"); cited.append(e["eid"])
    for e in (e for e in ev if e["kind"] == "sql"):
        parts.append(f"From the records: {e['text'][:600]} [{e['eid']}]"); cited.append(e["eid"])
    q_ids = set(ID_RE.findall(state["question"]))
    trace_ids = set(ID_RE.findall(" ".join(e["text"] for e in trace_ev)))
    strong = []
    for e in (e for e in ev if e["kind"] == "chunk"):
        chunk_ids = set(ID_RE.findall(e["text"]))
        if not (e["coverage"] >= MIN_COVERAGE or q_ids & chunk_ids):
            continue
        # consistency rule: when the records produced a chain, drop document passages that are
        # about *other* entities (they'd put wrong IDs in the answer)
        if trace_ids and chunk_ids and not (chunk_ids & trace_ids):
            continue
        strong.append(e)
    for e in strong[:3]:
        parts.append(f"{_best_sentence(e['text'], q_terms)} [{e['eid']}]"); cited.append(e["eid"])
    if not parts:
        return {"answer": NO_EVIDENCE, "citations": [], "answerable": False}
    return {"answer": "\n".join(parts), "citations": cited, "answerable": True}

def report(state):
    with span("report", state["run_id"]):
        ev = state.get("evidence", [])
        if llm.available() and ev:
            try:
                blocks = "\n".join(f"[{e['eid']}] ({e['ref']}) {e['text']}" for e in ev)
                out = llm.generate_json(REPORT_PROMPT.format(q=state["question"], ev=blocks), state["run_id"], "report")
                if not out.get("answerable", True):
                    return {"answer": NO_EVIDENCE, "citations": [], "answerable": False, "answer_by": "llm"}
                return {"answer": out["answer"], "citations": out.get("citations", []),
                        "answerable": True, "answer_by": "llm"}
            except Exception:
                pass
        return {**extractive_answer(state), "answer_by": "extractive"}

REPORT_PROMPT = """Answer the engineering question using ONLY the evidence. Cite evidence IDs like [E2]
after each claim. Name the record IDs involved (REQ-, TC-, RES-, FAIL-, CR-) exactly as they appear in
the evidence. Document passages may be irrelevant to the question: ignore those, and when a passage
conflicts with the structured records, trust the records. If the evidence does not answer the
question, set answerable=false.
Question: {q}
Evidence:
{ev}
Return JSON: {{"answer": "...", "citations": ["E1", ...], "answerable": true}}"""

# ---------------- validate ----------------
def validate(state):
    ev = state.get("evidence", [])
    eids = {e["eid"] for e in ev}
    issues = []
    if state.get("answerable"):
        cited = set(state.get("citations", [])) | set(re.findall(r"\[(E\d+)\]", state.get("answer", "")))
        if not cited:
            issues.append("answer has no citations")
        if cited - eids:
            issues.append(f"cites unknown evidence {sorted(cited - eids)}")
        ev_text = " ".join(e["text"] + " " + e["ref"] for e in ev)
        invented = set(ID_RE.findall(state.get("answer", ""))) - set(ID_RE.findall(ev_text))
        if invented:
            issues.append(f"mentions IDs not in evidence {sorted(invented)}")
    upd = {"validation": {"passed": not issues, "issues": issues}}
    if issues and state.get("answer_by") == "llm":   # never ship an ungrounded LLM answer
        upd.update(extractive_answer(state), answer_by="extractive_fallback")
    return upd
