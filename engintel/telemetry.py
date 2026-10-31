"""Structured JSON logs to stdout. Cloud Run ships stdout to Cloud Logging as-is."""
import json
import sys
import time
import uuid
from contextlib import contextmanager

def new_run_id(prefix="run"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"

def log(**fields):
    fields.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
    print(json.dumps(fields, default=str), file=sys.stderr, flush=True)

@contextmanager
def span(node, run_id=None, **extra):
    """Times a step and logs latency + status. Swap for OpenTelemetry spans on GCP."""
    t0 = time.perf_counter()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        log(run_id=run_id, node=node, latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            status=status, **extra)
