import sqlite3
import pytest
from engintel import store
from engintel.agents import nodes
from engintel.chunk import chunk_elements
from engintel.sql_guard import UnsafeSQL, guard

@pytest.mark.parametrize("sql", ["DROP TABLE requirements", "SELECT 1; DELETE FROM requirements",
    "SELECT * FROM sqlite_master", "SELECT * FROM requirements -- sneaky", "UPDATE requirements SET status='x'"])
def test_guard_blocks_unsafe_sql(sql):
    with pytest.raises(UnsafeSQL):
        guard(sql)

def test_guard_adds_limit_and_allows_ctes():
    assert guard("SELECT req_id FROM requirements").endswith("LIMIT 200")
    guard("WITH x AS (SELECT req_id FROM requirements) SELECT * FROM x")

def test_readonly_connection_blocks_writes(use_built):
    with pytest.raises(sqlite3.OperationalError):
        store.query("DELETE FROM requirements", readonly=True)

def test_chunk_ids_deterministic_and_tables_whole():
    els = [{"page": 1, "section": "2 Limits", "element_type": "text", "text": "word " * 400},
           {"page": 1, "section": "2 Limits", "element_type": "table", "text": "Table with columns: a, b."}]
    a, b = chunk_elements("doc1", "x.pdf", els), chunk_elements("doc1", "x.pdf", els)
    assert [c["chunk_id"] for c in a] == [c["chunk_id"] for c in b]
    assert sum(c["element_type"] == "table" for c in a) == 1

def test_validator_flags_invented_ids():
    state = {"answerable": True, "answer": "Caused by FAIL-999 [E1]", "citations": ["E1"],
             "evidence": [{"eid": "E1", "kind": "chunk", "ref": "x.pdf", "text": "FAIL-87 was logged"}]}
    v = nodes.validate(state)["validation"]
    assert not v["passed"] and "FAIL-999" in v["issues"][0]

def test_validator_flags_unknown_citation():
    state = {"answerable": True, "answer": "Something [E7]", "citations": ["E7"],
             "evidence": [{"eid": "E1", "kind": "chunk", "ref": "x.pdf", "text": "y"}]}
    assert not nodes.validate(state)["validation"]["passed"]

def test_agent_open_chains_and_refusal(use_built):
    from engintel.agents.graph import ask
    st = ask("Which requirements have failing tests linked to open change requests?")
    for r in use_built["gt"]["open_chain_requirements"]:
        assert r in st["answer"]
    assert "REQ-125" not in st["answer"]
    assert ask("What is the warranty period for the infotainment screen?")["answerable"] is False


def test_llm_reply_with_trailing_text_is_parsed():
    from engintel import llm
    assert llm.parse_json('```json\n{"answer": "x"}\n```\nHope this helps!') == {"answer": "x"}

def test_rate_limits_are_retried():
    from engintel import llm
    calls, waits = {"n": 0}, []
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "ok"
    assert llm.with_retry(flaky, base_delay=1, sleep=waits.append) == "ok" and waits == [1, 2]

def test_llm_mode_sees_low_overlap_passages(use_built, monkeypatch):
    """Real finding: the answer to 'What caused the HV-7 failures?' ('fretting corrosion') shares almost
    no words with the question, so the coverage filter dropped it before the LLM could see it."""
    from engintel import config
    from engintel.agents import nodes
    state = {"question": "What caused the HV-7 connector failures?", "run_id": "t", "evidence": [],
             "plan": {"tools": ["retrieval"], "ids": [], "by": "rules"}}
    extractive = nodes.retrieval_node(state)["evidence"]
    monkeypatch.setattr(config, "USE_LLM", True)
    with_llm = nodes.retrieval_node(state)["evidence"]
    assert not any("fretting" in e["text"] for e in extractive)
    assert any("fretting" in e["text"] for e in with_llm)
