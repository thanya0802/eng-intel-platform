"""python -m engintel.cli <command>"""
import argparse
import json
import shutil
from . import config, store
from .telemetry import new_run_id

def cmd_reset(_):
    for p in (config.DB_PATH, config.INDEX_DIR):
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    store.init_db(); print("reset warehouse + index")

def cmd_ingest(_):
    from .ingest import ingest_folder
    from .structured import load_structured
    store.init_db()
    s = load_structured(config.STRUCTURED_DIR, new_run_id("structured"))
    print("structured:", json.dumps(s))
    print("documents:", json.dumps(ingest_folder(config.RAW_DIR)))

def cmd_index(a):
    from .retrieval.index import build_index
    print(json.dumps(build_index(a.embedder)))

def cmd_ask(a):
    from .agents.graph import ask
    st = ask(a.question)
    print(f"plan: {st['plan']}  engine: {st['engine']}  answer_by: {st.get('answer_by')}")
    print("\n" + st["answer"] + "\n")
    for e in st.get("evidence", []):
        if e["eid"] in set(st.get("citations", [])):
            print(f"  [{e['eid']}] {e['ref']}")
    print(f"validation: {st['validation']}")

def cmd_trace(a):
    from .trace import trace
    for e in trace(a.entity_id):
        print(f"{e['src']:>9} -{e['rel']}-> {e['dst']}")

def cmd_quality(_):
    rows = store.query("""SELECT check_name, entity_id, details FROM quality_results WHERE passed=0
                          AND run_id=(SELECT run_id FROM quality_results ORDER BY checked_at DESC LIMIT 1)""")
    for r in rows:
        print(f"FAIL {r['check_name']:<28} {r['entity_id']:<36} {r['details']}")
    print("docs:", store.query("SELECT status, COUNT(*) n FROM documents GROUP BY status"))
    print("dlq:", store.query("SELECT payload, error, attempts FROM dlq"))

def main():
    p = argparse.ArgumentParser(prog="engintel")
    sp = p.add_subparsers(required=True)
    sp.add_parser("reset").set_defaults(fn=cmd_reset)
    sp.add_parser("ingest").set_defaults(fn=cmd_ingest)
    x = sp.add_parser("index"); x.add_argument("--embedder", default=None); x.set_defaults(fn=cmd_index)
    x = sp.add_parser("ask"); x.add_argument("question"); x.set_defaults(fn=cmd_ask)
    x = sp.add_parser("trace"); x.add_argument("entity_id"); x.set_defaults(fn=cmd_trace)
    sp.add_parser("quality").set_defaults(fn=cmd_quality)
    a = p.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
