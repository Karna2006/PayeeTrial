"""Submit & Verify: scenario loader, form, live run view, decision. The demo page."""
from __future__ import annotations

from dataclasses import asdict

import streamlit as st

from engine import documents, messages, pipeline, store
from ui import components as C
from ui import state

F = state.fkey


def _scenario_loader() -> None:
    scs = state.scenarios()
    pick, load, blank = st.columns([6, 1, 1.6], vertical_alignment="bottom")
    slug = pick.selectbox("Load demo scenario", list(scs), key="ui_scenario",
                          format_func=lambda s: f"{s[:2]} · {scs[s]['title']}")
    load.button("Load", key="btn_load", on_click=state.cb_load_scenario, width="stretch")
    blank.button("New blank form", key="btn_blank", on_click=state.cb_new_blank, width="stretch")
    note = " Run scenario 02 first: this is its resubmission." if slug.startswith("05") else ""
    st.caption(f"Expected outcome: {scs[slug]['expected']}.{note}")


def _form() -> tuple[bool, list]:
    ss = st.session_state
    top = st.columns([2, 3, 1.2], vertical_alignment="bottom")
    top[0].selectbox("Entity type", ["", *state.ENTITY_TYPES], key=F("entity_type"),
                     format_func=lambda v: v or "Select…")
    attached = ss["ui_attached"]
    top[1].markdown(f"Reference: `{ss['ui_ref']}`" + (
        f" · {len(attached)} document(s) attached from the demo scenario" if attached else ""))
    if attached:
        top[2].button("Clear attached", key="btn_clear_attached", on_click=state.cb_clear_attached, width="stretch")

    with st.form("submission", border=True):
        C.section("Company")
        c = st.columns(4)
        c[0].text_input("Legal name", key=F("legal_name"))
        c[1].text_input("Trade name (optional)", key=F("trade_name"))
        c[2].text_input("PAN", key=F("pan"), placeholder="AAAAA9999A")
        c[3].text_input("GSTIN", key=F("gstin"), placeholder="15 characters")
        if ss[F("entity_type")] == "Proprietorship":
            st.text_input("Proprietor's full name", key=F("proprietor_name"),
                          help="A proprietor and their business are the same legal person.")

        C.section("Address")
        c = st.columns(4)
        c[0].text_input("Address line 1", key=F("address.line1"))
        c[1].text_input("City", key=F("address.city"))
        c[2].selectbox("State", ["", *state.STATES], key=F("address.state"), format_func=lambda v: v or "Select…")
        c[3].text_input("PIN code", key=F("address.pincode"))

        C.section("Contact")
        c = st.columns(4)
        c[0].text_input("Contact name", key=F("contact.name"))
        c[1].text_input("Email", key=F("contact.email"))
        c[2].text_input("Phone", key=F("contact.phone"))
        c[3].text_input("Website (optional)", key=F("website"))

        C.section("Bank")
        c = st.columns(4)
        c[0].text_input("Account holder name", key=F("bank.account_holder"))
        c[1].text_input("Account number", key=F("bank.account_number"))
        c[2].text_input("IFSC", key=F("bank.ifsc"), placeholder="AAAA0XXXXXX")
        c[3].text_input("Bank name", key=F("bank.bank_name"))

        C.section("Documents")
        if attached:
            chips = "".join(f"<span class='vg-chip'>{name}</span>" for name in attached)
            st.markdown(f"Attached from demo scenario: {chips}", unsafe_allow_html=True)
        uploads = st.file_uploader("Upload PDFs (GST certificate, PAN card, cancelled cheque)", type=["pdf"],
                                   accept_multiple_files=True, key=f"ui_uploads_{ss['ui_upload_nonce']}")
        submitted = st.form_submit_button("▶ Run verification", type="primary", key="btn_run")
    return submitted, list(uploads or [])


def _read_documents(uploads: list) -> list[documents.ParsedDoc]:
    docs = []
    for name in st.session_state["ui_attached"]:
        path = state.SAMPLE_DOCS / name
        docs.append(documents.parse(name, path.read_bytes() if path.exists() else b""))
    docs += [documents.parse(u.name, u.getvalue()) for u in uploads]
    return docs


def _execute(uploads: list, prev: dict | None) -> dict:
    """Run the pipeline stage by stage, render it as it goes, then persist the run."""
    ss = st.session_state
    sub = state.build_submission([u.name for u in uploads])
    st.toast(f"Verifying {sub['legal_name'] or 'submission'}…")
    docs = _read_documents(uploads)
    doc_dicts = [{"filename": d.filename, "doc_type": d.doc_type, "fields": d.fields} for d in docs]
    previous = {k: prev[k] for k in ("submission", "results", "version")} if prev else None
    delay = 0.6 if ss["ui_pacing"] else 0.0

    C.section("Live run")
    C.doc_chips(doc_dicts)
    collected: list[pipeline.CheckResult] = []
    stage_ms: dict[str, float] = {}

    def stream():
        for key, label, results, ms in pipeline.run(sub, docs, state.load_master(), previous, delay=delay):
            collected.extend(results)
            stage_ms[key] = max(ms - delay * 1000, 0.0)  # report compute time, not demo pacing
            yield key, label, [asdict(r) for r in results], stage_ms[key]

    C.render_stages(stream())

    decision = pipeline.decide(collected)
    results = [asdict(r) for r in collected]
    email = messages.vendor_email(sub, decision, results)
    if ss["ui_polish"]:
        email = messages.polish_with_llm(email)
    note = messages.internal_note(decision, results)
    saved = store.save(sub["submission_ref"], pipeline.normalise_submission(sub), doc_dicts, results, decision,
                       email, note, round(sum(stage_ms.values()), 2))
    record = state.record_from_row(store.get_run(saved["run_id"]), stage_ms)
    ss["last_run"] = record
    ss["selected_run"] = saved["run_id"]
    st.toast(f"Saved as run #{saved['run_id']} (v{saved['version']})")
    return record


def render() -> None:
    st.title("Submit & Verify")
    st.caption("Run a vendor submission through 26 checks across 5 stages.")
    _scenario_loader()

    ss = st.session_state
    prev = store.latest(ss["ui_ref"])
    if prev:
        n = prev["version"] + 1
        C.banner(f"↻ Resubmission detected: this will be v{n} of {ss['ui_ref']} "
                 f"(v{n - 1} was {prev['status']} · {prev['queue']}).")

    submitted, uploads = _form()
    record = None
    if submitted:
        try:
            record = _execute(uploads, prev)
        except Exception as exc:  # the engine never swallows errors; the UI shows them kindly
            st.error(f"The verification run could not finish: {exc}")
    elif ss.get("last_run"):
        record = ss["last_run"]
        C.run_view(record)
    if record:
        C.decision_section(record)
