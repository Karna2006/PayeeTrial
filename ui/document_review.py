"""Streamlit view for audited, human-confirmed OCR/document extraction."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

import streamlit as st

from engine import messages, pipeline, reviews, store
from engine.documents import DOC_TYPES, ParsedDoc
from ui import state

_FIELDS = {
    "gst_certificate": ("gstin", "legal_name", "trade_name", "address", "status"),
    "pan_card": ("pan", "name"),
    "cancelled_cheque": ("ifsc", "account_number", "account_holder", "bank_name"),
}


def _parsed_doc(row: dict) -> ParsedDoc:
    return ParsedDoc(filename=row.get("filename", "document.pdf"), doc_type=row.get("doc_type", "unknown"),
                     text="", fields=dict(row.get("fields") or {}), warnings=list(row.get("warnings") or []),
                     page_count=row.get("page_count"), ai_review=row.get("ai_review"), page_texts=[],
                     sha256=row.get("sha256", ""), file_size=row.get("file_size", 0),
                     analyst_review=row.get("analyst_review"))


def render(record: dict) -> None:
    docs = record.get("docs") or []
    pending = [(index, doc) for index, doc in enumerate(docs)
               if (doc.get("ai_review") or {}).get("needs_review") and not doc.get("analyst_review")]
    history = record.get("review_history") or []
    if not pending and not history:
        return
    st.subheader("Document analyst review")
    if history:
        st.caption(f"{len(history)} analyst review event(s) recorded; original AI output remains in the audit history.")
        with st.expander("Review audit history", expanded=False):
            for event in history:
                payload = event.get("payload") or {}
                st.markdown(f"**{event.get('created_at', '')} · {event.get('reviewer', 'Analyst')}** — "
                            f"{event.get('reason', '')}")
                for audit_doc in payload.get("documents", []):
                    audit = audit_doc.get("analyst_review")
                    if audit:
                        st.caption(f"{audit_doc.get('filename')}: {audit.get('action')} · "
                                   f"{audit.get('original_doc_type')} → {audit.get('accepted_doc_type')}")
                        st.json({"reason": audit.get("reason"),
                                 "original_fields": audit.get("original_fields"),
                                 "accepted_fields": audit.get("accepted_fields")})
    if not pending:
        return

    for index, doc in pending:
        ai = doc.get("ai_review") or {}
        filename = str(doc.get("filename", "document.pdf"))
        sha256 = str(doc.get("sha256", ""))
        cached = st.session_state.get("review_pdf_bytes", {})
        pdf = cached.get((record["run_id"], sha256)) if sha256 else None
        with st.container(border=True):
            st.markdown(f"**{filename}** · {ai.get('review_reason') or 'AI extraction needs confirmation'}")
            if ai.get("fields"):
                st.caption("AI candidate values are unconfirmed: " + ", ".join(
                    f"{key}={value}" for key, value in ai["fields"].items() if value))
            if pdf:
                st.download_button("Open original PDF", data=pdf, file_name=filename,
                                   mime="application/pdf", key=f"review_pdf_{record['run_id']}_{index}")
            else:
                st.warning("The original PDF is no longer available in this browser session. Rerun the submission "
                           "with the document attached to review it.")
                continue

            suggested_type = ai.get("document_type")
            if suggested_type not in _FIELDS:
                suggested_type = doc.get("doc_type") if doc.get("doc_type") in _FIELDS else "gst_certificate"
            type_key = f"review_type_{record['run_id']}_{index}"
            selected_type = st.selectbox("Document type", list(_FIELDS),
                                         index=list(_FIELDS).index(suggested_type), key=type_key,
                                         format_func=lambda key: DOC_TYPES[key])
            candidates = {**(doc.get("fields") or {}), **(ai.get("fields") or {})}
            values: dict[str, str] = {}
            columns = st.columns(2)
            for field_index, field_name in enumerate(_FIELDS[selected_type]):
                values[field_name] = columns[field_index % 2].text_input(
                    field_name.replace("_", " ").title(), value=str(candidates.get(field_name) or ""),
                    key=f"review_field_{record['run_id']}_{index}_{selected_type}_{field_name}")
            reviewer = st.text_input("Reviewer name *", key=f"reviewer_{record['run_id']}_{index}")
            reason = st.text_area("Review reason *", key=f"review_reason_{record['run_id']}_{index}",
                                  placeholder="For example: visually checked the printed PAN and GSTIN against the PDF.")
            checked = st.checkbox("I checked these values against the original PDF", key=f"review_checked_{record['run_id']}_{index}")
            if st.button("Save analyst review and rerun checks", key=f"review_save_{record['run_id']}_{index}",
                         type="primary", disabled=not (reviewer.strip() and reason.strip() and checked)):
                try:
                    parsed = [_parsed_doc(d) for d in docs]
                    parsed[index] = reviews.confirm_document(parsed[index], doc_type=selected_type, fields=values,
                                                             reviewer=reviewer, reason=reason,
                                                             original_checked=checked)
                    outcome = pipeline.run_all(record["submission"], parsed, state.load_master(),
                                               state.previous_of(store.get_run(record["run_id"])))
                    now = datetime.now().isoformat(timespec="seconds")
                    email = messages.vendor_email(record["submission"], outcome["decision"], outcome["results"])
                    note = messages.internal_note(outcome["decision"], outcome["results"])
                    note = (note + "\n\nAnalyst document review: " + reviewer.strip() + " — " + reason.strip()).strip()
                    payload = {"created_at": now, "reviewer": reviewer.strip(), "reason": reason.strip(),
                               "documents": [asdict(d) for d in parsed], "results": outcome["results"],
                               "decision": outcome["decision"], "email": email, "internal_note": note}
                    store.add_analyst_review(record["run_id"], reviewer.strip(), reason.strip(), payload)
                    st.session_state["last_run"] = state.record_from_row(store.get_run(record["run_id"]))
                    st.toast("Analyst review saved; checks rerun on confirmed values.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
