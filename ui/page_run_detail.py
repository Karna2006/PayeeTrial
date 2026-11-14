"""Run detail: the complete audit record of one run, plus every version of that submission."""
from __future__ import annotations

import streamlit as st

from engine import pipeline, store
from engine.documents import DOC_TYPES
from ui import components as C
from ui import document_review
from ui import state
from ui.page_dashboard import run_label


def _version_history(runs: list[dict], current: dict) -> None:
    versions = sorted((r for r in runs if r["submission_ref"] == current["submission_ref"]),
                      key=lambda r: r["version"])
    st.subheader(f"Version history for {current['submission_ref']}")
    for r in versions:
        c = st.columns([0.6, 1.8, 1.6, 2.2, 1, 1], vertical_alignment="center")
        c[0].markdown(f"**v{r['version']}**")
        c[1].markdown(str(r["created_at"]).replace("T", " "))
        c[2].markdown(C.status_pill(r["status"]), unsafe_allow_html=True)
        c[3].markdown(r["queue"])
        c[4].markdown(f"rule {r['risk_score']}")
        if r["run_id"] == current["run_id"]:
            c[5].caption("shown below")
        else:
            c[5].button("Open", key=f"v_open_{r['run_id']}", on_click=state.cb_goto,
                        args=("Run detail", r["run_id"]), width="stretch")


def render() -> None:
    st.title("Run detail")
    runs = store.all_runs()
    if not runs:
        st.info("No runs yet. Go to Submit & Verify and load a demo scenario.")
        st.button("Go to Submit & Verify", key="btn_detail_go", type="primary",
                  on_click=state.cb_goto, args=("Submit & Verify",))
        return

    by_id = {r["run_id"]: r for r in runs}
    if st.session_state.get("selected_run") not in by_id:
        st.session_state["selected_run"] = runs[0]["run_id"]  # newest
    run_id = st.selectbox("Run", list(by_id), key="selected_run", format_func=lambda i: run_label(by_id[i]))
    row = by_id[run_id]
    record = state.record_from_row(row)

    C.decision_card(record["decision"], record)
    if record.get("original_decision"):
        st.caption(f"Original automated result: {record['original_decision']['status']} · "
                   f"rule score {record['original_decision']['risk_score']}. Analyst review is separately audited.")
    _version_history(runs, row)

    checks, facts = st.columns([3, 2])
    with checks:
        st.subheader("Checks by stage")
        C.render_stages(iter(record["stages"]))
    with facts:
        st.subheader("Documents")
        C.doc_chips(record["docs"])
        for d in record["docs"]:
            st.markdown(f"`{d['filename']}` · {DOC_TYPES.get(d['doc_type'], d['doc_type'])}")
            C.kv_table(d.get("fields") or {})
            if d.get("autofill_fields"):
                st.caption("Form autofill provenance")
                st.json(d["autofill_fields"])
        st.subheader("Submission")
        C.kv_table(pipeline._flatten(record["submission"]))

    C.result_tabs(record)
    document_review.render(record)
