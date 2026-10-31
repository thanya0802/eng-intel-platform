"""Traceability is deterministic SQL, not LLM reasoning.
The agent decides WHAT to trace; this code does the tracing, so chains are always correct."""
from . import store

LINKS_SQL = """
WITH links(src, dst, rel) AS (
  SELECT req_id, tc_id, 'verified_by' FROM test_cases
  UNION ALL SELECT tc_id, result_id, 'executed_as' FROM test_results
  UNION ALL SELECT result_id, fail_id, 'produced_failure' FROM failure_logs
  UNION ALL SELECT fail_id, cr_id, 'addressed_by' FROM change_requests WHERE fail_id <> ''
)"""

def trace(entity_id, direction="both", max_depth=6):
    """Recursive walk over the link graph from any ID (REQ/TC/RES/FAIL/CR)."""
    edges = []
    if direction in ("down", "both"):
        edges += store.query(LINKS_SQL + """,
          walk(node, src, dst, rel, depth) AS (
            SELECT dst, src, dst, rel, 1 FROM links WHERE src = ?
            UNION ALL
            SELECT l.dst, l.src, l.dst, l.rel, w.depth + 1 FROM links l JOIN walk w ON l.src = w.node
            WHERE w.depth < ?)
          SELECT DISTINCT src, dst, rel, depth FROM walk ORDER BY depth""", (entity_id, max_depth))
    if direction in ("up", "both"):
        edges += store.query(LINKS_SQL + """,
          walk(node, src, dst, rel, depth) AS (
            SELECT src, src, dst, rel, 1 FROM links WHERE dst = ?
            UNION ALL
            SELECT l.src, l.src, l.dst, l.rel, w.depth + 1 FROM links l JOIN walk w ON l.dst = w.node
            WHERE w.depth < ?)
          SELECT DISTINCT src, dst, rel, -depth AS depth FROM walk ORDER BY depth""", (entity_id, max_depth))
    return edges

def failing_chains(cr_status="open"):
    """Requirement -> test -> failed result -> failure -> change request (status filter)."""
    return store.query("""
      SELECT r.req_id, r.title AS requirement, tc.tc_id, tr.result_id, tr.run_date,
             f.fail_id, f.severity, cr.cr_id, cr.status AS cr_status, cr.title AS change_request
      FROM requirements r
      JOIN test_cases tc ON tc.req_id = r.req_id
      JOIN test_results tr ON tr.tc_id = tc.tc_id AND tr.outcome = 'fail'
      JOIN failure_logs f ON f.result_id = tr.result_id
      JOIN change_requests cr ON cr.fail_id = f.fail_id
      WHERE (? = 'any' OR cr.status = ?)
      ORDER BY r.req_id, tc.tc_id""", (cr_status, cr_status))

def coverage():
    return store.query("""
      SELECT r.req_id, r.subsystem, r.priority,
        COUNT(DISTINCT tc.tc_id) AS tests,
        SUM(CASE WHEN tr.outcome='fail' THEN 1 ELSE 0 END) AS failed_runs,
        SUM(CASE WHEN tr.outcome='pass' THEN 1 ELSE 0 END) AS passed_runs
      FROM requirements r LEFT JOIN test_cases tc ON tc.req_id = r.req_id
      LEFT JOIN test_results tr ON tr.tc_id = tc.tc_id
      GROUP BY r.req_id ORDER BY r.req_id""")

def entity_exists(entity_id):
    for table, key in store.STRUCTURED_TABLES.items():
        if store.query(f"SELECT 1 FROM {table} WHERE {key}=?", (entity_id,)):
            return table
    return None
