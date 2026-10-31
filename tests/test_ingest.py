"""Failure-injection tests: duplicates, corrupt files, transient errors, crash + resume."""

from engintel import config, store
from engintel.ingest import (LocalQueue, SimulatedCrash, backfill, handle,
                             ingest_folder)

def test_duplicate_upload_creates_one_document(env):
    res = ingest_folder(config.RAW_DIR)
    assert res["skipped"] == 1                         # the _COPY.pdf has identical bytes
    n = store.query("SELECT COUNT(*) n FROM documents WHERE source LIKE 'battery_thermal%'")[0]["n"]
    assert n == 1

def test_reupload_after_success_is_noop(env):
    ingest_folder(config.RAW_DIR)
    before = store.query("SELECT COUNT(*) n FROM chunks")[0]["n"]
    res = ingest_folder(config.RAW_DIR)
    assert res["processed"] == 0
    assert store.query("SELECT COUNT(*) n FROM chunks")[0]["n"] == before

def test_corrupt_pdf_lands_in_dlq_with_reason(env):
    ingest_folder(config.RAW_DIR)
    dlq = store.query("SELECT payload, error, attempts FROM dlq")
    assert len(dlq) == 1 and "corrupt_upload.pdf" in dlq[0]["payload"]
    assert dlq[0]["attempts"] == config.MAX_DELIVERY_ATTEMPTS
    assert "unreadable PDF" in dlq[0]["error"]
    assert store.query("SELECT status FROM documents WHERE source='corrupt_upload.pdf'")[0]["status"] == "failed"

def test_scan_like_pdf_flagged_for_ocr(env):
    ingest_folder(config.RAW_DIR)
    row = store.query("SELECT status, error FROM documents WHERE source='scanned_wiring_diagram.pdf'")[0]
    assert row["status"] == "needs_ocr"

def test_transient_error_is_retried_then_succeeds(env):
    calls = {"n": 0}
    def flaky(event, run_id):
        calls["n"] += 1
        return handle(event, run_id, fault="warehouse_timeout" if calls["n"] <= 2 else None)
    q = LocalQueue()
    q.publish({"uri": str(config.RAW_DIR / "brake_by_wire_requirements.pdf")})
    stats = q.drain(flaky, "t-retry")
    assert stats == {"processed": 1, "skipped": 0, "dead_lettered": 0, "retried": 2}
    assert store.query("SELECT COUNT(*) n FROM dlq")[0]["n"] == 0

def test_persistent_transient_error_dead_letters(env):
    q = LocalQueue()
    q.publish({"uri": str(config.RAW_DIR / "brake_by_wire_requirements.pdf")})
    stats = q.drain(lambda e, r: handle(e, r, fault="warehouse_timeout"), "t-dlq")
    assert stats["dead_lettered"] == 1 and stats["retried"] == config.MAX_DELIVERY_ATTEMPTS - 1

def test_crashed_backfill_resumes_from_checkpoint(env):
    uris = sorted(str(p) for p in config.RAW_DIR.glob("*.pdf"))
    try:
        backfill(uris, "bf-1", crash_after=7)
        raise AssertionError("expected crash")
    except SimulatedCrash:
        pass
    cp = store.query("SELECT last_completed_index FROM checkpoints WHERE run_id='bf-1'")[0]
    assert cp["last_completed_index"] == 5             # checkpoint lags real progress (6 done)
    out = backfill(uris, "bf-1")
    assert out["start_index"] == 6
    assert out["results"][0] == "skipped_duplicate"    # item 6 redone safely thanks to content hash
    srcs = store.query("SELECT source, COUNT(*) n FROM documents GROUP BY source HAVING n > 1")
    assert srcs == []

def test_reprocessing_replaces_chunks(env):
    ingest_folder(config.RAW_DIR)
    before = store.query("SELECT COUNT(*) n FROM chunks")[0]["n"]
    with store.tx() as con:
        con.execute("UPDATE documents SET status='pending'")   # force a full reprocess
    ingest_folder(config.RAW_DIR)
    assert store.query("SELECT COUNT(*) n FROM chunks")[0]["n"] == before
