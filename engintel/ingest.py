"""Document ingestion worker + a local queue with Pub/Sub delivery semantics.

handle(event) is the exact body of the Cloud Run /pubsub endpoint:
  content hash = identity -> duplicate uploads are skipped
  success -> 2xx (ack)          failure -> raise (nack) -> redelivery with backoff
  after MAX_DELIVERY_ATTEMPTS -> dead-letter queue, with the error recorded
"""
import hashlib
import json
import time
import uuid
from pathlib import Path
from . import config, store
from .chunk import chunk_elements, doc_title
from .parse import ParseError, parse_pdf
from .telemetry import log, span

class RetryableError(Exception):
    """Transient (network, quota, timeout). Redelivery may succeed."""

class SimulatedCrash(Exception):
    """Used by failure-injection tests to kill a backfill mid-run."""

def read_object(uri: str) -> bytes:
    # local "bucket"; on GCP: storage.Client().bucket(b).blob(name).download_as_bytes()
    return Path(uri).read_bytes()

TERMINAL = ("processed", "needs_ocr")   # needs_ocr waits for the OCR path; re-parsing can't help

def already_processed(doc_id):
    rows = store.query("SELECT status FROM documents WHERE doc_id=?", (doc_id,))
    return bool(rows) and rows[0]["status"] in TERMINAL

def process_document(doc_id, uri, content, run_id, fault=None):
    source = Path(uri).name
    with span("parse", run_id, doc_id=doc_id[:12]):
        elements, n_pages = parse_pdf(content)
    if fault == "warehouse_timeout":
        raise RetryableError("simulated warehouse timeout")
    chunks = chunk_elements(doc_id, source, elements, title=doc_title(elements))
    with store.tx() as con:
        con.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))  # reprocess replaces, never appends
        for c in chunks:
            store.upsert(con, "chunks", {**c, "embedding_model": None}, "chunk_id")
            store.record_lineage(con, c["chunk_id"], "chunk", uri, doc_id, "parse+chunk",
                                 config.PARSER_VERSION, run_id)
        ocr_pages = sorted({e["page"] for e in elements if e["element_type"] == "needs_ocr"})
        store.upsert(con, "documents", dict(
            doc_id=doc_id, uri=uri, doc_type="pdf", source=source, ingested_at=store.now(),
            status="processed" if not ocr_pages or chunks else "needs_ocr",
            parser_version=config.PARSER_VERSION,
            error=f"pages needing OCR: {ocr_pages}" if ocr_pages else None, pages=n_pages), "doc_id")
    return len(chunks)

def mark_failed(doc_id, uri, err):
    with store.tx() as con:
        store.upsert(con, "documents", dict(doc_id=doc_id, uri=uri, doc_type="pdf",
                     source=Path(uri).name, ingested_at=store.now(), status="failed",
                     parser_version=config.PARSER_VERSION, error=err, pages=None), "doc_id")

def handle(event: dict, run_id: str, fault=None) -> dict:
    uri = event["uri"]
    content = read_object(uri)
    doc_id = hashlib.sha256(content).hexdigest()
    if already_processed(doc_id):
        log(run_id=run_id, node="ingest", status="skipped_duplicate", doc_id=doc_id[:12], uri=uri)
        return {"status": "skipped_duplicate", "doc_id": doc_id}
    try:
        n = process_document(doc_id, uri, content, run_id, fault=fault)
    except RetryableError:
        raise
    except ParseError as e:
        mark_failed(doc_id, uri, str(e))
        raise
    log(run_id=run_id, node="ingest", status="processed", doc_id=doc_id[:12], chunks=n)
    return {"status": "processed", "doc_id": doc_id, "chunks": n}

class LocalQueue:
    """In-process stand-in for a Pub/Sub push subscription with a dead-letter topic."""
    def __init__(self, max_attempts=config.MAX_DELIVERY_ATTEMPTS, sleep=False):
        self.msgs, self.max_attempts, self.sleep = [], max_attempts, sleep

    def publish(self, event):
        self.msgs.append({"id": uuid.uuid4().hex[:12], "event": event, "attempts": 0})

    def drain(self, handler, run_id):
        stats = {"processed": 0, "skipped": 0, "dead_lettered": 0, "retried": 0}
        while self.msgs:
            m = self.msgs.pop(0)
            m["attempts"] += 1
            try:
                res = handler(m["event"], run_id)
                stats["processed" if res["status"] == "processed" else "skipped"] += 1
            except Exception as e:
                if m["attempts"] >= self.max_attempts:
                    with store.tx() as con:
                        store.upsert(con, "dlq", dict(msg_id=m["id"], payload=json.dumps(m["event"]),
                                     error=f"{type(e).__name__}: {e}", attempts=m["attempts"],
                                     dead_at=store.now()), "msg_id")
                    stats["dead_lettered"] += 1
                    log(run_id=run_id, node="queue", status="dead_lettered", uri=m["event"]["uri"], error=str(e))
                else:
                    stats["retried"] += 1
                    if self.sleep:
                        time.sleep(min(10 * 2 ** (m["attempts"] - 1), 300))  # 10s..300s like retry_policy
                    self.msgs.append(m)
        return stats

def ingest_folder(folder: Path, trigger="manual"):
    """Equivalent of bucket notifications: every object -> one message."""
    store.init_db()
    run_id = f"ingest-{uuid.uuid4().hex[:8]}"
    q = LocalQueue()
    uris = sorted(str(p) for p in folder.glob("*.pdf"))
    for u in uris:
        q.publish({"uri": u})
    started = store.now()
    stats = q.drain(handle, run_id)
    with store.tx() as con:
        store.upsert(con, "pipeline_runs", dict(run_id=run_id, trigger=trigger, started_at=started,
                     finished_at=store.now(), docs_seen=len(uris), docs_processed=stats["processed"],
                     docs_skipped=stats["skipped"], docs_failed=stats["dead_lettered"]), "run_id")
    return {"run_id": run_id, "docs_seen": len(uris), **stats}

def backfill(uris, run_id, crash_after=None):
    """Checkpointed batch processing. Re-running the same run_id resumes after the checkpoint.
    Content hashing makes it safe even if the checkpoint lags behind real progress."""
    store.init_db()
    rows = store.query("SELECT last_completed_index FROM checkpoints WHERE run_id=?", (run_id,))
    start = rows[0]["last_completed_index"] + 1 if rows else 0
    done = []
    for i in range(start, len(uris)):
        if crash_after is not None and i == crash_after:
            raise SimulatedCrash(f"crashed before item {i}")
        try:
            done.append(handle({"uri": uris[i]}, run_id)["status"])
        except (ParseError, RetryableError) as e:
            done.append(f"failed: {e}")
        if i % config.CHECKPOINT_EVERY == 0 or i == len(uris) - 1:
            with store.tx() as con:
                store.upsert(con, "checkpoints", dict(run_id=run_id, last_completed_index=i,
                             updated_at=store.now()), "run_id")
    return {"start_index": start, "results": done}
