"""B · Rule-level tests: scenario 1 (clean) mutated one field at a time."""
from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter

from conftest import by_id, failed_ids, parse_docs, load_submission, warned_ids
from engine import documents, pipeline, validators as V
from engine.documents import ParsedDoc


def test_b1_blank_submission_does_not_crash(master):
    out = pipeline.run_all({}, [], master)
    req = by_id(out, "REQ_FIELDS")
    assert req["status"] == "fail" and len(req["evidence"]["missing"]) == len(pipeline.REQUIRED_FIELDS) == 15
    assert out["decision"]["status"] == "PENDING" and out["decision"]["queue"] == "Awaiting vendor"


def test_b2_proprietor_name_required(run_sample):
    out = run_sample(6, changes={"proprietor_name": ""})
    assert "Proprietor's full name" in by_id(out, "REQ_FIELDS")["evidence"]["missing"]


@pytest.mark.parametrize("changes, status, severity", [
    ({"contact.email": "accounts.nimbuslogistics.in"}, "fail", "blocker"),
    ({"contact.email": "accounts@"}, "fail", "blocker"),
    ({"contact.email": "@nimbuslogistics.in"}, "fail", "blocker"),
    ({"contact.email": "accounts@localhost"}, "fail", "blocker"),
    ({"contact.email": "nimbus.accounts@gmail.com"}, "warn", "warn"),
    ({"contact.email": "accounts@nimbusgroup.in"}, "warn", "warn"),
    ({"contact.email": "accounts@nimbuslogistics.in", "website": "https://www.nimbuslogistics.in/contact"}, "pass", "blocker"),
])
def test_b3_email(run_sample, changes, status, severity):
    email = by_id(run_sample(1, changes=changes), "EMAIL")
    assert email["status"] == status
    if status != "pass":
        assert email["severity"] == severity


def test_b3b_warnings_alone_still_approve(run_sample):
    out = run_sample(1, changes={"contact.email": "nimbus.accounts@gmail.com"})
    assert out["decision"]["status"] == "APPROVED" and out["decision"]["risk_score"] == 5
    assert "1 minor note(s)" in out["decision"]["headline"]


def test_b4_phone_and_pincode(run_sample):
    out = run_sample(1, changes={"contact.phone": "12345", "address.pincode": "056003"})
    assert {"PHONE", "PINCODE"} <= set(failed_ids(out))
    assert by_id(run_sample(1, changes={"contact.phone": "+91-98450-12345"}), "PHONE")["status"] == "pass"
    assert by_id(run_sample(1), "PINCODE") is None  # only emitted on failure


def test_b5_malformed_pan_skips_dependent_checks(run_sample):
    out = run_sample(1, changes={"pan": "AAAC4821K"})
    assert by_id(out, "PAN_FORMAT")["status"] == "fail"
    assert by_id(out, "PAN_TYPE") is None and by_id(out, "GSTIN_PAN_LINK") is None


def test_b5b_ids_are_normalised_before_checks(run_sample):
    out = run_sample(1, changes={"pan": "aaacn 4821k", "gstin": "29-aaacn4821k-1zb", "bank.ifsc": "hdfc0001234"})
    assert failed_ids(out) == [] and out["decision"]["status"] == "APPROVED"


def test_b6_pan_type_vs_entity(run_sample):
    out = run_sample(1, changes={"entity_type": "Proprietorship", "proprietor_name": "Priya Raman"})
    pan_type = by_id(out, "PAN_TYPE")
    assert pan_type["status"] == "fail" and pan_type["severity"] == "blocker"
    assert "belongs to a company" in pan_type["vendor_ask"]


def test_b6b_pan_initial_soft_warning(run_sample):
    out = run_sample(1, changes={"legal_name": "Zenith Logistics Private Limited"})
    assert "PAN_INITIAL" in warned_ids(out)


def test_b7_gstin_checksum_names_expected_char(run_sample):
    out = run_sample(1, changes={"gstin": "29AAACN4821K1ZC"})
    g = by_id(out, "GSTIN_VALID")
    assert g["status"] == "fail" and "expected 'B', got 'C'" in g["detail"]
    assert "checksum" in g["vendor_ask"]
    assert by_id(out, "GSTIN_PAN_LINK") is None and by_id(out, "GSTIN_STATE") is None  # stage stops


def test_b7b_gstin_malformed(run_sample):
    g = by_id(run_sample(1, changes={"gstin": "29AAACN4821K"}), "GSTIN_VALID")
    assert g["status"] == "fail" and "malformed" in g["vendor_ask"]


def test_b8_pan_two_chars_off_is_a_different_entity(run_sample):
    out = run_sample(1, changes={"pan": "AAACN4899K"})
    link = by_id(out, "GSTIN_PAN_LINK")
    assert link["severity"] == "reject" and "fraud-signal" in link["tags"]
    assert out["decision"]["status"] == "REJECTED" and "GSTIN_PAN_LINK" in out["decision"]["fraud_signals"]


def test_b8b_gstin_state_mismatch(run_sample):
    ask = by_id(run_sample(1, changes={"address.state": "Kerala"}), "GSTIN_STATE")["vendor_ask"]
    assert "Karnataka (state code 29)" in ask and "start with 32" in ask


def test_b9_ifsc_and_account_format(run_sample):
    out = run_sample(1, changes={"bank.ifsc": "HDFC1001234", "bank.account_number": "12345"})
    assert {"IFSC", "ACCOUNT_NO"} <= set(failed_ids(out))
    assert by_id(run_sample(1), "ACCOUNT_NO") is None
    assert "HDFC Bank" in by_id(run_sample(1), "IFSC")["detail"]


def test_b9b_ifsc_bank_mismatch_warns(run_sample):
    out = run_sample(1, changes={"bank.bank_name": "Canara Bank"})
    assert "IFSC_BANK" in warned_ids(out) and "risk-signal" in by_id(out, "IFSC_BANK")["tags"]


@pytest.mark.parametrize("holder, status, severity", [
    ("Nimbus Logistics India Pvt Ltd", "pass", None),          # 88.9  ≥ 88
    ("Nimbus Logistics Services Pvt Ltd", "fail", "blocker"),  # 84.2  in the ask band
    ("Nimbus Logistics", "fail", "blocker"),                   # 80.0
    ("Nimbus Transport Pvt Ltd", "fail", "reject"),            # 58.3  < 70
])
def test_b10_account_name_bands(run_sample, holder, status, severity):
    sim = V.name_similarity(holder, "Nimbus Logistics Private Limited")
    assert (sim >= 88) == (status == "pass") and (sim < 70) == (severity == "reject")  # guards the test data
    acct = by_id(run_sample(1, changes={"bank.account_holder": holder}), "ACCOUNT_NAME")
    assert acct["status"] == status
    if severity:
        assert acct["severity"] == severity


def test_b11_existing_vendor_is_a_duplicate(run_sample):
    pan = "AAACB1120F"  # V-1001 in the vendor master
    out = run_sample(1, changes={"pan": pan, "gstin": V.make_gstin("29", pan)})
    dup = by_id(out, "DUP_VENDOR")
    assert dup["severity"] == "reject" and "V-1001" in dup["internal_note"]
    assert "already registered" in dup["vendor_ask"] and "V-1001" not in dup["vendor_ask"]
    assert out["decision"]["status"] == "REJECTED"


def test_b11b_same_vendor_same_account_is_not_dup_bank(run_sample):
    pan = "AAACB1120F"
    out = run_sample(1, changes={"pan": pan, "gstin": V.make_gstin("29", pan), "bank.account_number": "60112233445"})
    assert by_id(out, "DUP_BANK")["status"] == "pass"


def test_b12_no_documents(run_sample):
    out = run_sample(1, docs=[])
    assert [i for i in failed_ids(out) if i.startswith("DOC_")] == [
        "DOC_GST_CERTIFICATE", "DOC_PAN_CARD", "DOC_CANCELLED_CHEQUE"]
    assert out["decision"]["queue"] == "Awaiting vendor"


def test_b13_unreadable_file_is_unknown(run_sample):
    junk = documents.parse("notes.pdf", b"this is not a pdf")
    assert junk.doc_type == "unknown" and junk.text == ""
    assert junk.warnings == ["File does not have a valid PDF header."]
    docs = parse_docs(load_submission(1)) + [junk]
    out = run_sample(1, docs=docs)
    assert warned_ids(out) == ["DOC_UNKNOWN"] and "notes.pdf" in by_id(out, "DOC_UNKNOWN")["detail"]
    assert out["decision"]["status"] == "APPROVED"


def test_b13a_document_intake_limits_and_encryption():
    large = documents.parse("large.pdf", b"%PDF-1.7\n" + b"0" * documents.MAX_DOCUMENT_BYTES)
    assert "exceeds" in large.warnings[0]

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    encrypted_pdf = io.BytesIO()
    writer.write(encrypted_pdf)
    encrypted = documents.parse("locked.pdf", encrypted_pdf.getvalue())
    assert encrypted.doc_type == "unknown"
    assert "encrypted" in encrypted.warnings[0]


def test_b13b_pdf_page_limit_is_reported():
    writer = PdfWriter()
    for _ in range(documents.MAX_PDF_PAGES + 1):
        writer.add_blank_page(width=100, height=100)
    pages_pdf = io.BytesIO()
    writer.write(pages_pdf)
    parsed = documents.parse("many-pages.pdf", pages_pdf.getvalue())
    assert parsed.page_count == documents.MAX_PDF_PAGES + 1
    assert "limit is" in parsed.warnings[0]


def test_b13c_pdf_without_selectable_text_is_flagged_for_ocr():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    blank_pdf = io.BytesIO()
    writer.write(blank_pdf)
    parsed = documents.parse("scan.pdf", blank_pdf.getvalue())
    assert parsed.doc_type == "unknown"
    assert parsed.page_count == 1
    assert "needs OCR" in parsed.warnings[0]


def test_b14_cancelled_gst_registration(run_sample):
    docs = parse_docs(load_submission(1))
    gst = next(d for d in docs if d.doc_type == "gst_certificate")
    docs[docs.index(gst)] = ParsedDoc(gst.filename, gst.doc_type, gst.text, {**gst.fields, "status": "Cancelled"})
    out = run_sample(1, docs=docs)
    assert "registration status is Cancelled" in by_id(out, "GST_DOC_MATCH")["detail"]


def test_b15_cheque_mismatch(run_sample):
    out = run_sample(1, changes={"bank.account_number": "50200012345679"})
    chq = by_id(out, "CHEQUE_MATCH")
    assert chq["status"] == "fail" and "50200012345678" in chq["vendor_ask"]


def test_b16_all_27_core_check_ids_are_reachable(run_sample):
    """Every check ID in Rules Spec §10 exists in the engine source."""
    spec = ("REQ_FIELDS EMAIL PHONE PINCODE PAN_FORMAT PAN_TYPE PAN_INITIAL GSTIN_VALID GSTIN_PAN_LINK GSTIN_STATE "
            "IFSC IFSC_BANK ACCOUNT_NO ACCOUNT_NAME DOC_UNKNOWN GST_DOC_MATCH PAN_DOC_MATCH CHEQUE_MATCH "
            "DUP_VENDOR DUP_BANK DUP_NAME_REVIEW RESUB_DIFF RESUB_BANK_CHANGE RESUB_CONTACT_CHANGE").split()
    source = open(pipeline.__file__, encoding="utf-8").read()
    assert all(f'"{check_id}"' in source for check_id in spec)
    doc_ids = {f"DOC_{t.upper()}" for t in pipeline.REQUIRED_DOCS}
    assert doc_ids == {"DOC_GST_CERTIFICATE", "DOC_PAN_CARD", "DOC_CANCELLED_CHEQUE"}
    assert len(spec) + len(doc_ids) == 27
    assert '"DOC_TYPE_CONFLICT"' in source


@pytest.mark.parametrize("doc_type,required_fields", [
    ("gst_certificate", {"gstin", "legal_name", "status"}),
    ("pan_card", {"pan", "name"}),
    ("cancelled_cheque", {"ifsc", "account_number", "account_holder"}),
])
def test_required_document_evidence_cannot_be_missing(run_sample, doc_type, required_fields):
    docs = parse_docs(load_submission(1))
    doc_index = next(i for i, doc in enumerate(docs) if doc.doc_type == doc_type)
    doc = docs[doc_index]
    docs[doc_index] = ParsedDoc(doc.filename, doc.doc_type, doc.text, {}, sha256=doc.sha256)

    out = run_sample(1, docs=docs)

    match_id = {"gst_certificate": "GST_DOC_MATCH", "pan_card": "PAN_DOC_MATCH",
                "cancelled_cheque": "CHEQUE_MATCH"}[doc_type]
    result = by_id(out, match_id)
    assert result["status"] == "fail" and result["severity"] == "review"
    assert set(result["evidence"]["missing_fields"]) == required_fields
    assert out["decision"]["status"] == "PENDING"


def test_different_pan_documents_block_until_vendor_resolves_conflict(run_sample):
    from dataclasses import replace

    docs = parse_docs(load_submission(1))
    pan_doc = next(doc for doc in docs if doc.doc_type == "pan_card")
    docs.append(replace(pan_doc, filename="second_pan.pdf", sha256="different-content",
                        fields={**pan_doc.fields, "pan": "AAACN4821J"}))

    out = run_sample(1, docs=docs)

    assert by_id(out, "DOC_TYPE_CONFLICT")["severity"] == "blocker"
    assert out["decision"]["queue"] == "Awaiting vendor"


def test_identical_ai_review_uploads_create_only_one_review_failure(run_sample):
    from dataclasses import replace

    docs = parse_docs(load_submission(1))
    pan_index = next(i for i, doc in enumerate(docs) if doc.doc_type == "pan_card")
    pan_doc = docs[pan_index]
    ai_review = {"needs_review": True, "review_reason": "Visual-only candidate needs confirmation.",
                 "model": "test-model"}
    docs[pan_index] = replace(pan_doc, ai_review=ai_review)
    docs.append(replace(pan_doc, filename="renamed-identical-pan.pdf", ai_review=ai_review))

    out = run_sample(1, docs=docs)

    assert len([r for r in out["results"] if r["check_id"] == "DOC_AI_REVIEW"]) == 1
    assert by_id(out, "DOC_DUPLICATE_FILE") is not None


def test_cheque_account_holder_must_match_form(run_sample):
    from dataclasses import replace

    docs = parse_docs(load_submission(1))
    index = next(i for i, doc in enumerate(docs) if doc.doc_type == "cancelled_cheque")
    cheque = docs[index]
    docs[index] = replace(cheque, fields={**cheque.fields, "account_holder": "Unrelated Person"})

    result = by_id(run_sample(1, docs=docs), "CHEQUE_MATCH")

    assert result["status"] == "fail" and "account holder" in result["detail"]


def test_pan_card_name_must_match_registered_entity(run_sample):
    from dataclasses import replace

    docs = parse_docs(load_submission(1))
    index = next(i for i, doc in enumerate(docs) if doc.doc_type == "pan_card")
    pan_doc = docs[index]
    docs[index] = replace(pan_doc, fields={**pan_doc.fields, "name": "Different Corporation"})

    result = by_id(run_sample(1, docs=docs), "PAN_DOC_MATCH")

    assert result["status"] == "fail" and "does not match registered name" in result["detail"]


def test_b17_proprietor_rule_when_legal_name_is_the_trade_name(run_sample):
    """The case a blunt 'holder != company -> reject' rule gets wrong."""
    acct = by_id(run_sample(6, changes={"legal_name": "Meera Prints"}), "ACCOUNT_NAME")
    assert acct["status"] == "pass" and "proprietor" in acct["detail"]
    blunt = by_id(run_sample(6, changes={"legal_name": "Meera Prints", "entity_type": "Partnership Firm"}), "ACCOUNT_NAME")
    assert blunt["status"] == "fail" and blunt["severity"] == "reject"
