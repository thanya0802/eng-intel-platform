from engintel import store, trace

def failed_checks():
    rows = store.query("SELECT check_name, entity_id FROM quality_results WHERE passed=0")
    return {f"{r['check_name']}:{r['entity_id']}" for r in rows}

def test_quality_checks_catch_planted_bad_data(use_built):
    assert set(use_built["gt"]["expected_quality_failures"]) <= failed_checks()
    for req in use_built["gt"]["uncovered_requirements"]:
        assert f"requirement_has_tests:{req}" in failed_checks()

def test_rejected_row_did_not_overwrite_good_row(use_built):
    assert store.query("SELECT title FROM requirements WHERE req_id='REQ-129'")[0]["title"]

def test_open_failing_chains_match_ground_truth(use_built):
    got = sorted({c["req_id"] for c in trace.failing_chains("open")})
    assert got == use_built["gt"]["open_chain_requirements"]

def test_trace_upstream_from_change_request(use_built):
    edges = trace.trace("CR-12", direction="up")
    assert {"REQ-104", "TC-204", "FAIL-87"} <= {e["src"] for e in edges}

def test_lineage_recorded_for_every_chunk(use_built):
    missing = store.query("""SELECT COUNT(*) n FROM chunks c WHERE NOT EXISTS
        (SELECT 1 FROM lineage l WHERE l.entity_id = c.chunk_id)""")[0]["n"]
    assert missing == 0
