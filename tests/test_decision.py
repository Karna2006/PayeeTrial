"""C · Decision precedence, resubmission behaviour, messages, determinism, performance."""
from __future__ import annotations

import time

import pytest

from conftest import as_previous, by_id, failed_ids, warned_ids
from engine import messages, pipeline
from engine.pipeline import CheckResult, decide


def check(status: str, severity: str, check_id: str = "X", detail: str = "d", tags=None) -> CheckResult:
    return CheckResult(check_id, "intake", check_id, status, detail, severity, tags=tags or [])


def test_c1_most_severe_signal_wins():
    d = decide([check("fail", "blocker"), check("fail", "review", detail="review first"),
                check("fail", "reject", detail="reject first", tags=["fraud-signal"]),
                check("fail", "reject", detail="reject second")])
    assert (d["status"], d["queue"], d["headline"]) == ("REJECTED", "Closed: rejected", "reject first")
    d = decide([check("fail", "blocker"), check("fail", "review", detail="review first")])
    assert (d["status"], d["queue"], d["headline"]) == ("PENDING", "Compliance review", "review first")
    d = decide([check("fail", "blocker"), check("fail", "blocker"), check("pass", "blocker")])
    assert (d["status"], d["queue"]) == ("PENDING", "Awaiting vendor")
    assert d["headline"] == "2 item(s) the vendor needs to fix" and (d["n_pass"], d["n_fail"]) == (1, 2)


def test_c2_stacked_warnings_go_to_procurement_review():
    d = decide([check("warn", "warn")] * 6)
    assert (d["status"], d["queue"], d["risk_score"]) == ("PENDING", "Procurement review", 30)
    d = decide([check("warn", "warn")] * 5)
    assert (d["status"], d["risk_score"]) == ("APPROVED", 25)


@pytest.mark.parametrize("n_warn, score, level", [(0, 0, "Low"), (3, 15, "Low"), (4, 20, "Medium"), (9, 45, "Medium"),
                                                   (10, 50, "High"), (30, 100, "High")])
def test_c3_risk_levels_and_cap(n_warn, score, level):
    d = decide([check("warn", "warn")] * n_warn)
    assert (d["risk_score"], d["risk_level"]) == (score, level)


def test_c3b_info_and_pass_carry_no_risk():
    d = decide([check("info", "info"), check("pass", "blocker")])
    assert d["risk_score"] == 0 and d["status"] == "APPROVED"
    assert d["headline"] == "All identity, bank, document and fraud checks passed"


def test_c4_identical_resubmission(run_sample):
    first = run_sample(1)
    out = run_sample(1, previous=as_previous(first["submission"], first))
    diff = by_id(out, "RESUB_DIFF")
    assert diff["status"] == "info" and diff["detail"] == "Changed: nothing" and "v2 vs v1" in diff["name"]
    assert by_id(out, "RESUB_BANK_CHANGE") is None and out["decision"]["status"] == "APPROVED"


def test_c5_requested_bank_change_is_fine(run_sample):
    first = run_sample(1, changes={"bank.account_number": "50200012345679"})  # cheque mismatch → we asked
    assert "CHEQUE_MATCH" in failed_ids(first)
    out = run_sample(1, previous=as_previous(first["submission"], first))
    change = by_id(out, "RESUB_BANK_CHANGE")
    assert change["status"] == "pass" and "earlier request" in change["detail"]
    assert out["decision"]["status"] == "APPROVED"


def test_c6_contact_swap(run_sample):
    first = run_sample(1)
    prev = as_previous(first["submission"], first)
    both = run_sample(1, previous=prev, changes={"contact.phone": "9000011111",
                                                 "contact.email": "new@nimbuslogistics.in"})
    assert "RESUB_CONTACT_CHANGE" in warned_ids(both)
    one = run_sample(1, previous=prev, changes={"contact.phone": "9000011111"})
    assert "RESUB_CONTACT_CHANGE" not in warned_ids(one)


def test_c7_phone_reformatting_is_not_a_change(run_sample):
    first = run_sample(1)  # phone '+91 98450 12345'
    out = run_sample(1, previous=as_previous(first["submission"], first),
                     changes={"contact.phone": "9845012345", "contact.email": "new@nimbuslogistics.in"})
    assert by_id(out, "RESUB_DIFF")["evidence"]["changed"] == ["contact.email"]
    assert "RESUB_CONTACT_CHANGE" not in warned_ids(out)


def test_c8_classify_changes_requested_vs_unrequested(run_sample):
    v1, v2 = run_sample(2), run_sample(5)
    rows = {r["field"]: r for r in pipeline.classify_changes(v1["submission"], v2["submission"], v1["results"])}
    assert set(rows) == {"pan", "gstin", "bank.account_number", "bank.ifsc", "bank.bank_name"}
    assert rows["pan"]["requested"] and rows["gstin"]["requested"]
    assert not any(rows[f]["requested"] for f in rows if f.startswith("bank."))
    assert (rows["pan"]["before"], rows["pan"]["after"]) == ("AAACR7731P", "AAACR7781P")
    assert pipeline.classify_changes(v1["submission"], v1["submission"], v1["results"]) == []


def test_c9_email_templates(run_sample):
    def email_for(n, **kw):
        out = run_sample(n, **kw)
        return messages.vendor_email(out["submission"], out["decision"], out["results"])

    approved = email_for(1)
    assert approved["subject"] == "Vendor onboarding approved: Nimbus Logistics Private Limited [VS-2026-101]"
    assert approved["to"] == "accounts@nimbuslogistics.in" and approved["body"].startswith("Hi Priya Raman,")
    assert approved["body"].endswith("Thanks,\nProcurement Team") and approved["polished_by"] == "template"

    pending = email_for(2)
    assert pending["subject"] == "Action needed: 3 item(s) to complete your vendor registration [VS-2026-102]"
    assert all(f"  {i}. " in pending["body"] for i in (1, 2, 3)) and "resubmit with reference VS-2026-102" in pending["body"]

    rejected = email_for(3)
    assert rejected["subject"] == "Update on your vendor registration [VS-2026-103]"
    assert len(rejected["asks"]) == 1  # DUP_BANK has no vendor ask by design


def test_c9b_rejection_with_no_safe_ask_stays_generic(run_sample):
    out = run_sample(1, changes={"bank.account_number": "34567890123"})  # V-1042's account, name still matches
    assert out["decision"]["status"] == "REJECTED" and out["decision"]["fraud_signals"] == ["DUP_BANK"]
    email = messages.vendor_email(out["submission"], out["decision"], out["results"])
    assert "V-1042" not in email["body"] and "Kaveri" not in email["body"]


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6])
def test_c12_deterministic(run_sample, n):
    runs = [run_sample(n) for _ in range(3)]
    assert runs[0]["results"] == runs[1]["results"] == runs[2]["results"]
    assert runs[0]["decision"] == runs[1]["decision"] == runs[2]["decision"]


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6])
def test_c13_pipeline_under_500ms(run_sample, n):
    t0 = time.perf_counter()
    run_sample(n)
    assert (time.perf_counter() - t0) * 1000 < 500
