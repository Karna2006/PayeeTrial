"""Submit & Verify: scenario loader, form, live run view, decision. The demo page."""
from __future__ import annotations

from dataclasses import asdict
import copy

import streamlit as st

from engine import autofill, documents, messages, pipeline, store
from services import document_ai
from ui import components as C
from ui import document_review
from ui import provider_settings
from ui import state

F = state.fkey


def _over_document_limit(attached_count: int, upload_count: int) -> bool:
    return (attached_count < 0 or upload_count < 0
            or attached_count + upload_count > documents.MAX_DOCUMENTS_PER_SUBMISSION)


def _scenario_loader() -> None:
    scs = state.scenarios()
    stories = {
        "01": "Clean submission; the form and documents agree.",
        "02": "A valid PAN and GSTIN disagree across fields and state.",
        "03": "A third-party bank account links to another vendor.",
        "04": "The form looks right, but the document contents do not.",
        "05": "A resubmission changes the bank without being asked.",
        "06": "A proprietor uses their own personal bank account.",
    }
    header, blank = st.columns([5, 1.5], vertical_alignment="bottom")
    header.markdown("### Choose a demo case")
    blank.button("New blank form", key="btn_blank", on_click=state.cb_new_blank, width="stretch")
    st.caption("Each case uses synthetic data and loads its form and sample PDFs.")
    slugs = list(scs)
    for row_start in range(0, len(slugs), 3):
        columns = st.columns(3)
        for column, slug in zip(columns, slugs[row_start:row_start + 3]):
            scenario = scs[slug]
            with column.container(border=True):
                st.markdown(f"**{slug[:2]} | {scenario['title']}**")
                st.caption(stories.get(slug[:2], "Synthetic submission for the demo."))
                st.caption(f"Expected result: {scenario['expected']}")
                if slug.startswith("05"):
                    st.caption("Run case 02 first; this is its resubmission.")
                st.button("Load case", key=f"btn_load_{slug}", on_click=state.cb_load_scenario,
                          args=(slug,), width="stretch")
    # Keep the list control as an accessible fallback and for existing saved demo workflows.
    with st.expander("Choose a case from the list", expanded=False):
        pick, load = st.columns([5, 1])
        slug = pick.selectbox("Load demo scenario", list(scs), key="ui_scenario",
                              format_func=lambda s: f"{s[:2]} | {scs[s]['title']}")
        load.button("Load", key="btn_load", on_click=state.cb_load_scenario, width="stretch")


def _form() -> tuple[bool, list, bool, list[str]]:
    ss = st.session_state
    attached = ss["ui_attached"]
    top = st.columns([4, 1.2], vertical_alignment="bottom")
    top[0].markdown(f"Reference: `{C.md_safe(ss['ui_ref'])}`" + (
        f" | {len(attached)} sample document(s) attached" if attached else ""))
    if attached:
        top[1].button("Clear attached", key="btn_clear_attached", on_click=state.cb_clear_attached,
                      width="stretch")

    st.caption("Fields marked * are required. Changes are checked as you complete the submission.")

    C.section("Company")
    c = st.columns(2)
    c[0].text_input("Legal name *", key=F("legal_name"), on_change=state.cb_form_changed)
    c[1].text_input("Trade name (optional)", key=F("trade_name"), on_change=state.cb_form_changed)
    c = st.columns(2)
    c[0].selectbox("Entity type *", ["", *state.ENTITY_TYPES], key=F("entity_type"),
                   format_func=lambda v: v or "Select...", on_change=state.cb_form_changed)
    c[1].text_input("PAN *", key=F("pan"), placeholder="AAAAA9999A", on_change=state.cb_form_changed)
    if ss[F("entity_type")] == "Proprietorship":
        st.text_input("Proprietor's full name *", key=F("proprietor_name"),
                      help="A proprietor and their business are the same legal person.",
                      on_change=state.cb_form_changed)
    st.text_input("GSTIN *", key=F("gstin"), placeholder="15 characters", on_change=state.cb_form_changed)

    C.section("Address")
    c = st.columns(2)
    c[0].text_input("Address line 1 *", key=F("address.line1"), on_change=state.cb_form_changed)
    c[1].text_input("City *", key=F("address.city"), on_change=state.cb_form_changed)
    c = st.columns(2)
    c[0].selectbox("State *", ["", *state.STATES], key=F("address.state"),
                   format_func=lambda v: v or "Select...", on_change=state.cb_form_changed)
    c[1].text_input("PIN code *", key=F("address.pincode"), on_change=state.cb_form_changed)

    C.section("Contact")
    c = st.columns(2)
    c[0].text_input("Contact name *", key=F("contact.name"), on_change=state.cb_form_changed)
    c[1].text_input("Email *", key=F("contact.email"), on_change=state.cb_form_changed)
    c = st.columns(2)
    c[0].text_input("Phone *", key=F("contact.phone"), on_change=state.cb_form_changed)
    c[1].text_input("Website (optional)", key=F("website"), on_change=state.cb_form_changed)

    C.section("Bank")
    c = st.columns(2)
    c[0].text_input("Account holder name *", key=F("bank.account_holder"), on_change=state.cb_form_changed)
    c[1].text_input("Account number *", key=F("bank.account_number"), on_change=state.cb_form_changed)
    c = st.columns(2)
    c[0].text_input("IFSC *", key=F("bank.ifsc"), placeholder="AAAA0XXXXXX", on_change=state.cb_form_changed)
    c[1].text_input("Bank name *", key=F("bank.bank_name"), on_change=state.cb_form_changed)

    C.section("Documents")
    st.caption(f"Add one PDF to each required slot; up to {documents.MAX_DOCUMENTS_PER_SUBMISSION} PDFs total. "
               "The engine checks document contents. AI review sends selected PDFs to OpenRouter; email polish sends "
               "the generated email body, which may include names, references, and correction requests. "
               "The free endpoint may log prompts or use them to improve provider products. Use synthetic data only.")
    attached_slots = state.attached_sample_slots(attached)
    columns = st.columns(3)
    uploads = []
    missing_documents = []
    for column, (slot, label) in zip(columns, state.DOCUMENT_SLOTS):
        uploaded = column.file_uploader(
            f"{label} *", type=["pdf"], accept_multiple_files=False,
            key=f"ui_upload_{slot}_{ss['ui_upload_nonce']}", on_change=state.cb_form_changed,
        )
        if uploaded:
            uploads.append(uploaded)
        if attached_slots[slot]:
            column.caption("Scenario attachment: " + ", ".join(attached_slots[slot]))
        elif not uploaded:
            missing_documents.append(label)

    additional = st.file_uploader(
        "Additional supporting PDFs (optional)", type=["pdf"], accept_multiple_files=True,
        key=f"ui_upload_additional_{ss['ui_upload_nonce']}", on_change=state.cb_form_changed,
    )
    uploads.extend(additional or [])
    autofill_clicked = st.button(
        "Autofill fields from documents", key="btn_autofill",
        disabled=not bool(uploads or attached),
        help="Read uploaded PDFs and fill blank matching fields. Existing values are kept.",
    )
    _show_autofill_report()
    too_many_documents = _over_document_limit(len(attached), len(uploads))
    if too_many_documents:
        st.error(f"A submission can contain at most {documents.MAX_DOCUMENTS_PER_SUBMISSION} PDFs. Remove extra files to continue.")

    missing_fields = state.missing_required_fields(ss)
    if missing_fields or missing_documents or too_many_documents:
        blocking_items = []
        if missing_fields:
            blocking_items.append("Required fields: " + ", ".join(missing_fields))
        if missing_documents:
            blocking_items.append("Required documents: " + ", ".join(missing_documents))
        if too_many_documents:
            blocking_items.append(f"At most {documents.MAX_DOCUMENTS_PER_SUBMISSION} PDFs are allowed.")
        st.error("Cannot run verification yet. " + " ".join(blocking_items))

    submitted = st.button(
        "Run verification", type="primary", key="btn_run",
        disabled=bool(missing_fields or missing_documents or too_many_documents), width="stretch",
    )
    return submitted, uploads, autofill_clicked, missing_documents

def _auto_fill_uploaded_documents(uploads: list) -> bool:
    """Read the attached/uploaded PDFs, then defer widget updates to the next rerun."""
    ss = st.session_state
    use_ai = bool(ss.get("ui_ai_review"))
    cached_docs = []
    for name in ss.get("ui_attached", []):
        path = state.SAMPLE_DOCS / name
        data = path.read_bytes() if path.exists() else b""
        cached_docs.append((data, documents.parse(name, data)))
    for upload in uploads:
        data = upload.getvalue()
        cached_docs.append((data, documents.parse(upload.name, data)))
    signature = (use_ai, provider_settings.model_name(),
                 tuple((doc.sha256, doc.filename) for _, doc in cached_docs))
    ss["autofill_upload_signature"] = signature
    if not cached_docs:
        ss["autofill_report"] = None
        return False

    extraction_errors = []
    if use_ai:
        model = provider_settings.model_name()
        review_cache = ss.setdefault("autofill_review_cache", {})
        with st.spinner("Reading documents and preparing field suggestions…"):
            for data, doc in cached_docs:
                if doc.warnings and not doc.page_count:
                    extraction_errors.append({"filename": doc.filename, "message": doc.warnings[0]})
                    continue
                cached_review = review_cache.get(doc.sha256)
                if cached_review:
                    document_ai.apply_review(doc, copy.deepcopy(cached_review))
                    continue
                try:
                    review = document_ai.review_pdf(data, provider_settings.openrouter_key(), page_count=doc.page_count,
                                                    text_layer=doc.text, page_texts=doc.page_texts, model=model)
                    review_cache[doc.sha256] = copy.deepcopy(review)
                    document_ai.apply_review(doc, review)
                except document_ai.DocumentAIError as exc:
                    extraction_errors.append({"filename": doc.filename, "message": str(exc)})
                    doc.ai_review = {"status": "unavailable", "provider": "OpenRouter", "model": model,
                                     "message": str(exc), "needs_review": not bool(doc.text.strip()),
                                     "review_reason": ("Scanned PDF needs manual review because AI review was unavailable."
                                                       if not doc.text.strip() else "")}
    else:
        for _, doc in cached_docs:
            if not doc.text.strip():
                message = (doc.warnings[0] if doc.warnings and not doc.page_count else
                           "No selectable text found. Enable AI document review for OCR suggestions.")
                extraction_errors.append({"filename": doc.filename, "message": message})
    ss["autofill_pending_errors"] = extraction_errors
    ss["autofill_pending"] = autofill.suggestions_from_docs([doc for _, doc in cached_docs])
    st.rerun()
    return True


def _show_autofill_report() -> None:
    report = st.session_state.get("autofill_report")
    if report is None:
        return
    st.subheader("Document field suggestions")
    st.caption("Blank fields are filled from uploaded documents. Existing values are kept; review every suggestion before submitting.")
    for error in report.get("errors", []):
        st.warning(f"{error['filename']}: {error['message']}")
    audit = report.get("audit") or []
    if not audit:
        if not report.get("errors"):
            st.info("No supported field values were found in the uploaded documents.")
        return
    for item in audit:
        field_name = item["field"]
        candidates = item["suggestions"]
        if item["status"] == "conflict":
            details = "; ".join(f"{candidate['value']} ({candidate['filename']})" for candidate in candidates)
            st.warning(f"Conflicting documents for {field_name}; nothing was filled. Review: {details}")
            continue
        for candidate in candidates:
            if item["status"] == "auto_filled":
                page = f", page {candidate['page_number']}" if candidate.get("page_number") else ""
                st.caption(f"Filled {field_name} from {candidate['filename']}{page}: {candidate['value']} · "
                           f"{candidate['source']}")
                if candidate.get("requires_confirmation") and candidate.get("quote"):
                    st.caption(f"OCR evidence: “{candidate['quote']}”")
            elif item["status"] == "existing_value_kept":
                st.warning(f"Kept the value already entered for {field_name}; {candidate['filename']} "
                           f"suggests {candidate['value']}.")
            elif item["status"] == "already_matches":
                st.caption(f"{field_name} matches {candidate['filename']} ({candidate['source']}).")


def _read_documents(uploads: list, use_ai: bool = False) -> list[documents.ParsedDoc]:
    docs = []
    raw_files = []
    for name in st.session_state["ui_attached"]:
        path = state.SAMPLE_DOCS / name
        data = path.read_bytes() if path.exists() else b""
        docs.append(documents.parse(name, data))
        raw_files.append(data)
    for upload in uploads:
        data = upload.getvalue()
        docs.append(documents.parse(upload.name, data))
        raw_files.append(data)
    if use_ai:
        api_key = provider_settings.openrouter_key()
        model = provider_settings.model_name()
        review_cache = st.session_state.get("autofill_review_cache", {})
        with st.spinner("AI is reviewing document content and page evidence…"):
            for doc, data in zip(docs, raw_files):
                if doc.warnings and not doc.page_count:
                    doc.ai_review = {"status": "skipped", "provider": "OpenRouter", "model": model,
                                     "message": "PDF could not be safely opened for AI review."}
                    continue
                cached_review = review_cache.get(doc.sha256)
                if cached_review:
                    document_ai.apply_review(doc, copy.deepcopy(cached_review))
                    continue
                try:
                    review = document_ai.review_pdf(data, api_key, page_count=doc.page_count,
                                                    text_layer=doc.text, page_texts=doc.page_texts, model=model)
                    document_ai.apply_review(doc, review)
                except document_ai.DocumentAIError as exc:
                    doc.ai_review = {"status": "unavailable", "provider": "OpenRouter", "model": model,
                                     "message": str(exc), "needs_review": not bool(doc.text.strip()),
                                     "review_reason": ("Scanned PDF could not be reviewed; analyst confirmation is required."
                                                       if not doc.text.strip() else "")}
                    doc.warnings.append("AI review unavailable; local PDF extraction was used.")
    return docs


def _execute(uploads: list, prev: dict | None, missing_documents: list[str]) -> dict:
    """Run the pipeline stage by stage, render it as it goes, then persist the run."""
    ss = st.session_state
    missing_fields = state.missing_required_fields(ss)
    too_many_documents = _over_document_limit(len(ss.get("ui_attached", [])), len(uploads))
    if missing_fields or missing_documents or too_many_documents:
        blocking_items = []
        if missing_fields:
            blocking_items.append("required fields: " + ", ".join(missing_fields))
        if missing_documents:
            blocking_items.append("required documents: " + ", ".join(missing_documents))
        if too_many_documents:
            blocking_items.append(f"no more than {documents.MAX_DOCUMENTS_PER_SUBMISSION} PDFs")
        st.error("Verification was not started. Complete " + "; ".join(blocking_items) + ".")
        return {}
    sub = state.build_submission([u.name for u in uploads])
    normalised_sub = pipeline.normalise_submission(sub)
    st.toast(f"Verifying {sub['legal_name'] or 'submission'}…")
    docs = _read_documents(uploads, use_ai=bool(ss.get("ui_ai_review")))
    pdf_bytes = [((state.SAMPLE_DOCS / name).read_bytes() if (state.SAMPLE_DOCS / name).exists() else b"")
                 for name in ss["ui_attached"]]
    pdf_bytes.extend(upload.getvalue() for upload in uploads)
    autofill_report = ss.get("autofill_report") or {}
    autofill_by_filename = {}
    for item in autofill_report.get("audit", []):
        for candidate in item.get("suggestions", []):
            autofill_by_filename.setdefault(candidate["filename"], []).append({
                "form_field": item["field"], "suggested_value": candidate["value"],
                "final_value": pipeline.get(normalised_sub, item["field"]), "source_field": candidate["source_field"],
                "source": candidate["source"], "page_number": candidate.get("page_number"),
                "quote": candidate.get("quote", ""), "status": item["status"],
            })
    doc_dicts = [{"filename": d.filename, "doc_type": d.doc_type, "fields": d.fields,
                  "warnings": d.warnings, "page_count": d.page_count, "ai_review": d.ai_review,
                  "sha256": d.sha256, "file_size": d.file_size, "analyst_review": d.analyst_review,
                  "autofill_fields": autofill_by_filename.get(d.filename, [])} for d in docs]
    previous = {k: prev[k] for k in ("submission", "results", "version")} if prev else None
    delay = 0.6 if ss["ui_pacing"] else 0.0

    C.section("Live run")
    C.doc_chips(doc_dicts)
    C.ai_document_reviews(doc_dicts)
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
    if ss.get("ui_ai_polish"):
        suggestion = messages.polish_with_openrouter(
            email, provider_settings.openrouter_key(), provider_settings.model_name())
        if suggestion.get("polished_by") != "template":
            email = {**email, "polish_suggestion": str(suggestion.get("body", ""))[:6000],
                     "polish_model": str(suggestion.get("polished_by", provider_settings.model_name()))[:120]}
        elif suggestion.get("polish_error"):
            email = {**email, "polish_error": suggestion["polish_error"]}
    note = messages.internal_note(decision, results)
    saved = store.save(sub["submission_ref"], normalised_sub, doc_dicts, results, decision,
                       email, note, round(sum(stage_ms.values()), 2))
    record = state.record_from_row(store.get_run(saved["run_id"]), stage_ms)
    ss["last_run"] = record
    ss["selected_run"] = saved["run_id"]
    ss["review_pdf_bytes"] = {
        (saved["run_id"], doc.sha256): data
        for doc, data in zip(docs, pdf_bytes)
        if doc.sha256 and doc.ai_review and doc.ai_review.get("needs_review")
    }
    st.toast(f"Saved as run #{saved['run_id']} (v{saved['version']})")
    return record


def render() -> None:
    state.apply_pending_autofill()
    st.markdown("<div class='vg-eyebrow'>PAYEETRAIL&nbsp;&nbsp;/&nbsp;&nbsp;VENDOR OPERATIONS</div>",
                unsafe_allow_html=True)
    st.title("Submit & Verify")
    st.caption("Collect the evidence, cross-check the details, and keep every decision traceable.")
    with st.container(border=True):
        _scenario_loader()

    ss = st.session_state
    prev = store.latest(ss["ui_ref"])
    if prev:
        n = prev["version"] + 1
        C.banner(f"↻ Resubmission detected: this will be v{n} of {ss['ui_ref']} "
                 f"(v{n - 1} was {prev['status']} · {prev['queue']}).")

    submitted, uploads, autofill_clicked, missing_documents = _form()
    if autofill_clicked and _auto_fill_uploaded_documents(uploads):
        return
    record = None
    if submitted:
        try:
            record = _execute(uploads, prev, missing_documents)
        except Exception as exc:  # the engine never swallows errors; the UI shows them kindly
            st.error(f"The verification run could not finish: {exc}")
    elif ss.get("last_run"):
        record = ss["last_run"]
        C.run_view(record)
    if record:
        C.decision_section(record)
        document_review.render(record)
