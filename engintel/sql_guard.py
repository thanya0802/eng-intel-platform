"""Validate model-written SQL before it touches the warehouse. Defense in depth:
1) static checks here, 2) a read-only connection (SQLite mode=ro / BigQuery viewer SA)."""
import re

ALLOWED_TABLES = {"requirements", "test_cases", "test_results", "failure_logs", "change_requests",
                  "documents", "quality_results", "pipeline_runs"}
FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|truncate|grant)\b", re.I)

class UnsafeSQL(ValueError):
    pass

def guard(sql: str, max_rows=200) -> str:
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise UnsafeSQL("multiple statements")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise UnsafeSQL("only SELECT/WITH queries are allowed")
    if FORBIDDEN.search(s):
        raise UnsafeSQL(f"forbidden keyword: {FORBIDDEN.search(s).group(0)}")
    if "--" in s or "/*" in s:
        raise UnsafeSQL("comments are not allowed")
    cte_names = {m.lower() for m in re.findall(r"\b(\w+)\s+as\s*\(", s, re.I)}
    tables = {t.lower() for t in re.findall(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", s, re.I)}
    bad = tables - ALLOWED_TABLES - cte_names
    if bad:
        raise UnsafeSQL(f"table(s) not allowed: {sorted(bad)}")
    if not re.search(r"\blimit\s+\d+\s*$", s, re.I):
        s += f" LIMIT {max_rows}"
    return s
