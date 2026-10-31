"""FastAPI service. Read paths use the read-only warehouse connection.
Run: uvicorn api.main:app --reload --port 8000"""
import shutil
import time
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from engintel import config, store, trace
from engintel.agents.graph import ask
from engintel.ingest import LocalQueue, handle
from engintel.telemetry import log, new_run_id

app = FastAPI(title="Engineering Intelligence & Traceability API", version="0.1.0")

class AskIn(BaseModel):
    question: str

@app.get("/health")
def health():
    return {"ok": True, "llm": config.USE_LLM, "embedder": config.EMBEDDER}

@app.post("/ask")
def ask_ep(body: AskIn):
    t0 = time.perf_counter()
    st = ask(body.question)
    cited = set(st.get("citations", []))
    resp = {"answer": st["answer"], "answerable": st.get("answerable"), "plan": st["plan"],
            "answer_by": st.get("answer_by"), "engine": st.get("engine"), "validation": st["validation"],
            "citations": [e for e in st.get("evidence", []) if e["eid"] in cited],
            "sql": st.get("sql"), "run_id": st["run_id"]}
    log(run_id=st["run_id"], node="api_ask", latency_ms=round((time.perf_counter() - t0) * 1000, 1), status="ok")
    return resp

@app.get("/trace/{entity_id}")
def trace_ep(entity_id: str):
    if not trace.entity_exists(entity_id):
        raise HTTPException(404, f"{entity_id} not found in requirements, tests, results, failures or change requests")
    return {"entity_id": entity_id, "edges": trace.trace(entity_id)}

@app.get("/chains")
def chains(status: str = "open"):
    return trace.failing_chains(status)

@app.get("/coverage")
def coverage():
    return trace.coverage()

@app.get("/quality")
def quality():
    return store.query("""SELECT run_id, check_name, entity_id, passed, details, checked_at
                          FROM quality_results ORDER BY checked_at DESC LIMIT 500""")

@app.get("/lineage/{entity_id}")
def lineage(entity_id: str):
    return store.query("SELECT * FROM lineage WHERE entity_id=? ORDER BY created_at", (entity_id,))

@app.get("/pipeline")
def pipeline():
    return {"runs": store.query("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 50"),
            "documents": store.query("SELECT source, status, error, pages, ingested_at FROM documents ORDER BY source"),
            "dlq": store.query("SELECT msg_id, payload, error, attempts, dead_at FROM dlq")}

@app.post("/upload")
def upload(file: UploadFile = File(...)):
    """Local stand-in for 'upload to GCS -> OBJECT_FINALIZE -> Pub/Sub push'."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "only PDF uploads are supported")
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.RAW_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    q = LocalQueue(); q.publish({"uri": str(dest)})
    stats = q.drain(handle, new_run_id("upload"))
    return {"file": file.filename, **stats, "note": "run `make index` to make new chunks searchable"}
