"""A · Scenario regression: the assertions required by docs/06_TEST_SCENARIOS.md."""
from __future__ import annotations

import pytest
from stdnum.in_ import gstin as std_gstin

from conftest import SAMPLES, SCENARIOS, as_previous, by_id, failed_ids, load_submission, warned_ids
from engine import documents, messages, validators as V


def status_queue_risk(out):
    d = out["decision"]
    return d["status"], d["queue"], d["risk_score"]


def test_a1_happy_path(run_sample):
    out = run_sample(1)
    assert status_queue_risk(out) == ("APPROVED", "Ready for vendor master", 0)
    assert failed_ids(out) == [] and warned_ids(out) == []
    assert out["decision"]["risk_level"] == "Low"


def test_a2_cross_field(run_sample):
    out = run_sample(2)
    assert status_queue_risk(out) == ("PENDING", "Awaiting vendor", 36)
    assert failed_ids(out) == ["GSTIN_PAN_LINK", "GSTIN_STATE", "PAN_DOC_MATCH"]
    assert by_id(out, "GSTIN_PAN_LINK")["severity"] == "blocker"
    assert "looks like a typo" in by_id(out, "GSTIN_PAN_LINK")["vendor_ask"]
    assert "should start with 27" in by_id(out, "GSTIN_STATE")["vendor_ask"]
    email = messages.vendor_email(out["submission"], out["decision"], out["results"])
    assert len(email["asks"]) == 3 and "3 item(s)" in email["subject"]


def test_a3_third_party_bank(run_sample):
    out = run_sample(3)
    assert status_queue_risk(out) == ("REJECTED", "Closed: rejected", 100)
    assert out["decision"]["fraud_signals"] == ["ACCOUNT_NAME", "DUP_BANK"]
    assert warned_ids(out) == ["EMAIL", "IFSC_BANK"]
    assert by_id(out, "CHEQUE_MATCH")["status"] == "pass"
    assert out["decision"]["risk_level"] == "High"


def test_a4_wrong_documents(run_sample):
    out = run_sample(4)
    assert status_queue_risk(out) == ("PENDING", "Awaiting vendor", 36)
    assert failed_ids(out) == ["DOC_TYPE_CONFLICT", "DOC_CANCELLED_CHEQUE", "GST_DOC_MATCH"]
    assert "PAN card twice" in by_id(out, "DOC_CANCELLED_CHEQUE")["vendor_ask"]
    assert "33AAACV3391N1Z1" in by_id(out, "GST_DOC_MATCH")["vendor_ask"]


def test_a5_proprietorship(run_sample):
    out = run_sample(6)
    assert status_queue_risk(out) == ("APPROVED", "Ready for vendor master", 0)
    acct = by_id(out, "ACCOUNT_NAME")
    assert acct["status"] == "pass" and "proprietor" in acct["detail"]
    assert by_id(out, "EMAIL")["status"] == "pass"  # free-mail is fine for a proprietorship


def test_a6_resubmission_bank_swap(run_sample):
    first = run_sample(2)
    out = run_sample(5, previous=as_previous(first["submission"], first))
    assert status_queue_risk(out) == ("PENDING", "Compliance review", 35)
    assert failed_ids(out) == ["RESUB_BANK_CHANGE"]
    assert out["decision"]["fraud_signals"] == ["RESUB_BANK_CHANGE"]
    assert by_id(out, "RESUB_DIFF")["evidence"]["changed"] == [
        "bank.account_number", "bank.bank_name", "bank.ifsc", "gstin", "pan"]
    note = messages.internal_note(out["decision"], out["results"])
    assert "9822012345" in note and "ORIGINAL number" in note
    email = messages.vendor_email(out["submission"], out["decision"], out["results"])
    assert email["asks"] == [] and "under review" in email["subject"]
    assert "bank" not in email["body"].lower()  # no tip-off


def test_a7_scenario_5_alone_is_clean(run_sample):
    assert status_queue_risk(run_sample(5)) == ("APPROVED", "Ready for vendor master", 0)


def test_a8_no_internal_leak_to_vendor(run_sample):
    out = run_sample(3)
    email = messages.vendor_email(out["submission"], out["decision"], out["results"])
    note = messages.internal_note(out["decision"], out["results"])
    vendor_text = email["subject"] + email["body"] + " ".join(email["asks"])
    assert "V-1042" not in vendor_text and "Kaveri" not in vendor_text
    assert "V-1042" in note


def test_a9_gstin_checksum_matches_stdnum(master):
    gstins = [load_submission(n)["gstin"] for n in SCENARIOS] + list(master["gstin"])
    gstins += ["33AAACV3391N1Z1", "29AAACN4821K1ZC", "27AAACR7781P1ZA"]  # sister cert + two bad checksums
    for g in gstins:
        assert V.gstin_checksum_valid(g) == std_gstin.is_valid(g), g
    assert all(V.gstin_checksum_valid(load_submission(n)["gstin"]) for n in SCENARIOS)


@pytest.mark.parametrize("pdf", sorted(p.name for p in (SAMPLES / "docs").glob("*.pdf")))
def test_a10_classified_by_content(pdf):
    doc = documents.parse(pdf, (SAMPLES / "docs" / pdf).read_bytes())
    if pdf == "synthetic_scan_pan.pdf":
        expected = "unknown"  # its visible text is intentionally image-only
    elif pdf == "vertex_cancelled_cheque.pdf":
        expected = "pan_card"  # the filename lies
    elif "gst_certificate" in pdf:
        expected = "gst_certificate"
    elif "cancelled_cheque" in pdf:
        expected = "cancelled_cheque"
    else:
        expected = "pan_card"
    assert doc.doc_type == expected


def test_a10b_eighteen_synthetic_pdfs():
    assert len(list((SAMPLES / "docs").glob("*.pdf"))) == 18


def test_a11_name_normalisation():
    assert V.normalize_name("A.B.C. Pvt. Ltd.") == V.normalize_name("ABC Private Limited")
    assert V.name_similarity("NIMBUS LOGISTICS PVT. LTD.", "Nimbus Logistics Private Limited") == 100
    assert V.name_similarity("Kaveri Traders", "Sunrise Office Supplies Private Limited") < 70
