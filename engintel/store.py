"""Warehouse layer. SQLite locally; same tables map 1:1 to BigQuery dataset `eng_intel`.

Every write is an UPSERT (INSERT ... ON CONFLICT DO UPDATE), the SQLite equivalent of
BigQuery MERGE. That is what makes retries safe: re-running a write can't duplicate rows.
"""
import sqlite3
import time
from contextlib import contextmanager
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(
  doc_id TEXT PRIMARY KEY, uri TEXT, doc_type TEXT, source TEXT, ingested_at TEXT,
  status TEXT, parser_version TEXT, error TEXT, pages INTEGER);
CREATE TABLE IF NOT EXISTS chunks(
  chunk_id TEXT PRIMARY KEY, doc_id TEXT, source TEXT, section TEXT, page INTEGER,
  element_type TEXT, text TEXT, chunk_index INTEGER, embedding_model TEXT);
CREATE TABLE IF NOT EXISTS lineage(
  entity_id TEXT, entity_type TEXT, source_uri TEXT, source_hash TEXT, transform TEXT,
  transform_version TEXT, run_id TEXT, created_at TEXT,
  PRIMARY KEY(entity_id, transform, source_hash));
CREATE TABLE IF NOT EXISTS quality_results(
  run_id TEXT, check_name TEXT, entity_id TEXT, passed INTEGER, details TEXT, checked_at TEXT);
CREATE TABLE IF NOT EXISTS pipeline_runs(
  run_id TEXT PRIMARY KEY, trigger TEXT, started_at TEXT, finished_at TEXT,
  docs_seen INTEGER DEFAULT 0, docs_processed INTEGER DEFAULT 0,
  docs_skipped INTEGER DEFAULT 0, docs_failed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS checkpoints(
  run_id TEXT PRIMARY KEY, last_completed_index INTEGER, updated_at TEXT);
CREATE TABLE IF NOT EXISTS dlq(
  msg_id TEXT PRIMARY KEY, payload TEXT, error TEXT, attempts INTEGER, dead_at TEXT);
CREATE TABLE IF NOT EXISTS requirements(
  req_id TEXT PRIMARY KEY, title TEXT, subsystem TEXT, priority TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS test_cases(tc_id TEXT PRIMARY KEY, req_id TEXT, title TEXT);
CREATE TABLE IF NOT EXISTS test_results(
  result_id TEXT PRIMARY KEY, tc_id TEXT, outcome TEXT, run_date TEXT);
CREATE TABLE IF NOT EXISTS failure_logs(
  fail_id TEXT PRIMARY KEY, result_id TEXT, tc_id TEXT, description TEXT, severity TEXT,
  logged_at TEXT);
CREATE TABLE IF NOT EXISTS change_requests(
  cr_id TEXT PRIMARY KEY, fail_id TEXT, title TEXT, status TEXT, opened_at TEXT);
"""

STRUCTURED_TABLES = {
    "requirements": "req_id", "test_cases": "tc_id", "test_results": "result_id",
    "failure_logs": "fail_id", "change_requests": "cr_id",
}

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def connect(readonly=False, db_path=None):
    path = db_path or config.DB_PATH
    if readonly:  # enforced by SQLite itself, not by our code
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    return con

def init_db():
    with connect() as con:
        con.executescript(SCHEMA)

@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()

def upsert(con, table, row: dict, key):
    keys = [key] if isinstance(key, str) else list(key)
    cols = list(row)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in keys) or f"{keys[0]}={keys[0]}"
    con.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
        f"ON CONFLICT({', '.join(keys)}) DO UPDATE SET {updates}",
        [row[c] for c in cols])

def query(sql, params=(), readonly=True):
    con = connect(readonly=readonly)
    try:
        cur = con.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()

def record_lineage(con, entity_id, entity_type, source_uri, source_hash, transform,
                   transform_version, run_id):
    upsert(con, "lineage", dict(entity_id=entity_id, entity_type=entity_type,
           source_uri=source_uri, source_hash=source_hash, transform=transform,
           transform_version=transform_version, run_id=run_id, created_at=now()),
           ("entity_id", "transform", "source_hash"))

def record_quality(con, run_id, check_name, entity_id, passed, details=""):
    con.execute("INSERT INTO quality_results VALUES (?,?,?,?,?,?)",
                (run_id, check_name, entity_id, int(passed), details, now()))
