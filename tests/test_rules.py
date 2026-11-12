"""B · Rule-level tests: scenario 1 (clean) mutated one field at a time."""
from __future__ import annotations

import pytest

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
    docs = parse_docs(load_submission(1)) + [junk]
    out = run_sample(1, docs=docs)
    assert warned_ids(out) == ["DOC_UNKNOWN"] and "notes.pdf" in by_id(out, "DOC_UNKNOWN")["detail"]
    assert out["decision"]["status"] == "APPROVED"


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


def test_b16_all_26_check_ids_are_reachable(run_sample):
    """Every check ID in Rules Spec §10 exists in the engine source."""
    spec = ("REQ_FIELDS EMAIL PHONE PINCODE PAN_FORMAT PAN_TYPE PAN_INITIAL GSTIN_VALID GSTIN_PAN_LINK GSTIN_STATE "
            "IFSC IFSC_BANK ACCOUNT_NO ACCOUNT_NAME DOC_UNKNOWN GST_DOC_MATCH PAN_DOC_MATCH CHEQUE_MATCH "
            "DUP_VENDOR DUP_BANK RESUB_DIFF RESUB_BANK_CHANGE RESUB_CONTACT_CHANGE").split()
    source = open(pipeline.__file__, encoding="utf-8").read()
    assert all(f'"{check_id}"' in source for check_id in spec)
    doc_ids = {f"DOC_{t.upper()}" for t in pipeline.REQUIRED_DOCS}
    assert doc_ids == {"DOC_GST_CERTIFICATE", "DOC_PAN_CARD", "DOC_CANCELLED_CHEQUE"}
    assert len(spec) + len(doc_ids) == 26


def test_b17_proprietor_rule_when_legal_name_is_the_trade_name(run_sample):
    """The case a blunt 'holder != company -> reject' rule gets wrong."""
    acct = by_id(run_sample(6, changes={"legal_name": "Meera Prints"}), "ACCOUNT_NAME")
    assert acct["status"] == "pass" and "proprietor" in acct["detail"]
    blunt = by_id(run_sample(6, changes={"legal_name": "Meera Prints", "entity_type": "Partnership Firm"}), "ACCOUNT_NAME")
    assert blunt["status"] == "fail" and blunt["severity"] == "reject"
