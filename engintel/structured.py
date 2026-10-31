"""Daily structured ingest: CSV -> validate -> upsert (MERGE) -> quality checks -> lineage.

Policy (say this in interviews):
  * file-level schema failure (wrong columns / malformed CSV) -> whole file rejected
  * row missing a required field -> row rejected, recorded in quality_results
  * duplicate key within a file -> last row wins, flagged
  * orphan reference (test -> missing requirement) -> loaded but flagged; real data is messy
    and dropping it would hide the problem from engineers
"""
import csv
import hashlib
import io
from datetime import date, timedelta
from pathlib import Path
from . import store
from .telemetry import log

TRANSFORM_VERSION = "structured-v1"

SCHEMAS = {  # table -> (columns, required)
    "requirements": (["req_id", "title", "subsystem", "priority", "status"], ["req_id", "title", "status"]),
    "test_cases": (["tc_id", "req_id", "title"], ["tc_id", "req_id"]),
    "test_results": (["result_id", "tc_id", "outcome", "run_date"], ["result_id", "tc_id", "outcome", "run_date"]),
    "failure_logs": (["fail_id", "result_id", "tc_id", "description", "severity", "logged_at"], ["fail_id", "result_id"]),
    "change_requests": (["cr_id", "fail_id", "title", "status", "opened_at"], ["cr_id", "status"]),
}
LOAD_ORDER = ["requirements", "test_cases", "test_results", "failure_logs", "change_requests"]

def read_csv_strict(path: Path, expected_cols):
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header != expected_cols:
        raise ValueError(f"header mismatch: expected {expected_cols}, got {header}")
    rows = []
    for lineno, r in enumerate(reader, start=2):
        if not r:
            continue
        if len(r) != len(expected_cols):
            raise ValueError(f"line {lineno}: expected {len(expected_cols)} fields, got {len(r)}")
        rows.append(dict(zip(expected_cols, (v.strip() for v in r))))
    return rows, hashlib.sha256(raw).hexdigest()

def load_structured(folder: Path, run_id: str):
    summary = {"loaded": {}, "rejected_rows": 0, "rejected_files": []}
    store.init_db()
    with store.tx() as con:
        # files that don't match any known table name are still checked (malformed drops)
        for f in sorted(folder.glob("*.csv")):
            table = f.stem.split("__")[0]          # test_results__late_batch.csv -> test_results
            if table not in SCHEMAS:
                store.record_quality(con, run_id, "file_schema", f.name, False, "unknown table name")
                summary["rejected_files"].append(f.name)
        for table in LOAD_ORDER:
            files = sorted(folder.glob(f"{table}.csv")) + sorted(folder.glob(f"{table}__*.csv"))
            for path in files:
                summary["loaded"][table] = summary["loaded"].get(table, 0) + _load_file(
                    con, run_id, table, path, summary)
        con.commit()
        run_integrity_checks(con, run_id)
    return summary

def _load_file(con, run_id, table, path, summary):
    cols, required = SCHEMAS[table]
    try:
        rows, file_hash = read_csv_strict(path, cols)
    except (ValueError, UnicodeDecodeError) as e:
        store.record_quality(con, run_id, "file_schema", path.name, False, str(e))
        summary["rejected_files"].append(path.name)
        log(run_id=run_id, node="structured_ingest", file=path.name, status="file_rejected", error=str(e))
        return 0
    store.record_quality(con, run_id, "file_schema", path.name, True)
    key = store.STRUCTURED_TABLES[table]
    seen, n = set(), 0
    for row in rows:
        missing = [c for c in required if not row.get(c)]
        ent = row.get(key) or "(no key)"
        if missing:
            store.record_quality(con, run_id, "required_fields", f"{table}:{ent}", False, f"missing {missing}")
            summary["rejected_rows"] += 1
            continue
        if row[key] in seen:
            store.record_quality(con, run_id, "duplicate_key", f"{table}:{ent}", False,
                                 "duplicate key in file; last row wins")
        seen.add(row[key])
        store.upsert(con, table, row, key)
        store.record_lineage(con, row[key], table, str(path), file_hash, "structured_ingest",
                             TRANSFORM_VERSION, run_id)
        n += 1
    return n

def run_integrity_checks(con, run_id, as_of=None, max_age_days=30):
    checks = [
        ("ref_integrity_test_to_req",
         "SELECT tc_id FROM test_cases WHERE req_id NOT IN (SELECT req_id FROM requirements)", "test case references missing requirement"),
        ("ref_integrity_result_to_test",
         "SELECT result_id FROM test_results WHERE tc_id NOT IN (SELECT tc_id FROM test_cases)", "result references missing test case"),
        ("ref_integrity_failure_to_result",
         "SELECT fail_id FROM failure_logs WHERE result_id NOT IN (SELECT result_id FROM test_results)",
         "failure references missing result"),
        ("ref_integrity_cr_to_failure",
         "SELECT cr_id FROM change_requests WHERE fail_id <> '' AND fail_id NOT IN (SELECT fail_id FROM failure_logs)",
         "CR references missing failure"),
        ("requirement_has_tests",
         "SELECT req_id FROM requirements WHERE req_id NOT IN (SELECT req_id FROM test_cases)", "requirement has no test coverage"),
    ]
    for name, sql, msg in checks:
        bad = [r[0] for r in con.execute(sql).fetchall()]
        if bad:
            for ent in bad:
                store.record_quality(con, run_id, name, ent, False, msg)
        else:
            store.record_quality(con, run_id, name, "*", True)
    latest = con.execute("SELECT MAX(run_date) FROM test_results").fetchone()[0]
    as_of = as_of or date.today()
    fresh = bool(latest) and date.fromisoformat(latest) >= as_of - timedelta(days=max_age_days)
    store.record_quality(con, run_id, "freshness_test_results", "*", fresh, f"latest run_date={latest}")
