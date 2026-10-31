"""Streamlit dashboard. Talks only to the API (same split as on Cloud Run).
Run: streamlit run dashboard/app.py   (API must be running on API_URL)"""
import os
import pandas as pd
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="Engineering intelligence", layout="wide")

def get(path, **params):
    r = requests.get(f"{API}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()

try:
    health = get("/health")
except Exception as e:
    st.error(f"Can't reach the API at {API}. Start it with `make api`, then reload. ({e})")
    st.stop()

st.title("Engineering intelligence & traceability")
st.caption(f"Fictional Program Halcyon data. Answers by: {'Gemini' if health['llm'] else 'extractive (no LLM key set)'}; "
           f"embedder: {health['embedder']}")

ask_tab, trace_tab, quality_tab, lineage_tab, pipe_tab = st.tabs(
    ["Ask", "Traceability", "Data quality", "Lineage", "Pipeline health"])

with ask_tab:
    examples = ["Which requirements have failing tests linked to open change requests?",
                "What is the brake response latency requirement?", "Trace REQ-104",
                "List the open change requests", "What is the warranty period for the infotainment screen?"]
    q = st.selectbox("Try an example or type your own below", examples)
    q = st.text_input("Question", value=q)
    if st.button("Get answer", type="primary") and q:
        r = requests.post(f"{API}/ask", json={"question": q}, timeout=120).json()
        st.markdown(r["answer"].replace("\n", "  \n"))
        st.write(f"Tools used: {', '.join(r['plan']['tools'])}. Grounding check: "
                 f"{'passed' if r['validation']['passed'] else 'failed ' + str(r['validation']['issues'])}")
        if r["citations"]:
            st.subheader("Sources")
            for c in r["citations"]:
                with st.expander(f"[{c['eid']}] {c['ref']}"):
                    st.write(c["text"])
        if r.get("sql") and r["sql"].get("query"):
            st.code(r["sql"]["query"], language="sql")

with trace_tab:
    status = st.radio("Change request status", ["open", "closed", "any"], horizontal=True)
    chains = pd.DataFrame(get("/chains", status=status))
    st.subheader(f"Failing chains ({len(chains)})")
    st.dataframe(chains, use_container_width=True, hide_index=True)
    cov = pd.DataFrame(get("/coverage"))
    c1, c2 = st.columns(2)
    c1.metric("Requirements without tests", int((cov["tests"] == 0).sum()))
    c2.metric("Requirements with a failed run", int((cov["failed_runs"] > 0).sum()))
    st.dataframe(cov, use_container_width=True, hide_index=True)
    ent = st.text_input("Trace any ID (REQ, TC, RES, FAIL, CR)", "CR-12")
    if ent:
        try:
            st.dataframe(pd.DataFrame(get(f"/trace/{ent}")["edges"]), hide_index=True)
        except requests.HTTPError:
            st.warning(f"{ent} isn't in the records. Check the ID and try again.")

with quality_tab:
    qdf = pd.DataFrame(get("/quality"))
    if qdf.empty:
        st.info("No quality results yet. Run `make ingest`.")
    else:
        st.metric("Check pass rate", f"{qdf['passed'].mean():.0%}")
        st.subheader("Failed checks")
        st.dataframe(qdf[qdf["passed"] == 0], use_container_width=True, hide_index=True)
        st.bar_chart(qdf.groupby("check_name")["passed"].mean())

with lineage_tab:
    ent = st.text_input("Record or chunk ID", "REQ-104")
    st.dataframe(pd.DataFrame(get(f"/lineage/{ent}")), use_container_width=True, hide_index=True)

with pipe_tab:
    p = get("/pipeline")
    d = pd.DataFrame(p["documents"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Documents processed", int((d["status"] == "processed").sum()) if not d.empty else 0)
    c2.metric("Waiting for OCR", int((d["status"] == "needs_ocr").sum()) if not d.empty else 0)
    c3.metric("Dead-letter queue", len(p["dlq"]))
    st.dataframe(d, use_container_width=True, hide_index=True)
    st.subheader("Dead-letter queue")
    st.dataframe(pd.DataFrame(p["dlq"]), use_container_width=True, hide_index=True)
    st.subheader("Runs")
    st.dataframe(pd.DataFrame(p["runs"]), use_container_width=True, hide_index=True)
    up = st.file_uploader("Upload a PDF", type="pdf")
    if up and st.button("Ingest upload"):
        st.json(requests.post(f"{API}/upload", files={"file": (up.name, up.getvalue())}, timeout=120).json())
