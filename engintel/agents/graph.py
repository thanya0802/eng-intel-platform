"""Wires the nodes. Uses LangGraph when installed; otherwise a plain sequential runner with
identical semantics (useful for minimal CI). Add a checkpointer (e.g. SqliteSaver / Postgres)
to make long runs resumable."""
from typing import Any, TypedDict
from ..telemetry import new_run_id
from . import nodes

ORDER = [("planner", nodes.planner), ("retrieval", nodes.retrieval_node), ("sql", nodes.sql_node),
         ("traceability", nodes.traceability_node), ("report", nodes.report), ("validate", nodes.validate)]

class State(TypedDict, total=False):
    question: str; run_id: str; plan: dict; evidence: list; hits: list; sql: dict; trace: dict
    answer: str; citations: list; answerable: bool; answer_by: str; validation: dict

_app = None
def _build():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None
    g = StateGraph(State)
    for name, fn in ORDER:
        g.add_node(name, fn)
    g.add_edge(START, ORDER[0][0])
    for (a, _), (b, _) in zip(ORDER, ORDER[1:]):
        g.add_edge(a, b)
    g.add_edge(ORDER[-1][0], END)
    return g.compile()

def ask(question: str) -> dict[str, Any]:
    global _app
    state = {"question": question, "run_id": new_run_id("ask"), "evidence": []}
    if _app is None:
        _app = _build() or "sequential"
    if _app != "sequential":
        state = _app.invoke(state)
        state["engine"] = "langgraph"
        return state
    for _, fn in ORDER:
        state.update(fn(state) or {})
    state["engine"] = "sequential"
    return state
