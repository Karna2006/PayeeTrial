from __future__ import annotations

from dataclasses import replace

import pytest
import pandas as pd

from conftest import load_submission, parse_docs
from engine import pipeline, reviews, store
from engine.documents import ParsedDoc


def test_confirmation_preserves_ai_candidate_and_records_accepted_values():
    original = ParsedDoc("scan.pdf", "unknown", "", {}, [], 1,
                         ai_review={"needs_review": True, "document_type": "pan_card",
                                    "fields": {"pan": "AAACN4821K", "name": "Nimbus Logistics"}})
    reviewed = reviews.confirm_document(original, doc_type="pan_card",
                                        fields={"pan": "aaacn 4821k", "name": "Nimbus Logistics"},
                                        reviewer="A. Reviewer", reason="Compared both printed fields with PDF.",
                                        original_checked=True, created_at="2026-11-12T12:00:00")
    assert original.doc_type == "unknown" and original.fields == {}
    assert original.ai_review["fields"]["pan"] == "AAACN4821K"
    assert reviewed.doc_type == "pan_card" and reviewed.fields["pan"] == "AAACN4821K"
    assert reviewed.ai_review == original.ai_review
    assert reviewed.analyst_review["action"] == "corrected"
    assert reviewed.analyst_review["reviewer"] == "A. Reviewer"


def test_confirmation_discards_unrecognized_fields_and_bounds_values():
    doc = ParsedDoc("scan.pdf", "unknown", "", {}, [], 1)
    reviewed = reviews.confirm_document(doc, doc_type="pan_card",
                                       fields={"pan": "AAACN4821K", "name": "Nimbus", "bank_account": "123"},
                                       reviewer="Reviewer", reason="Checked", original_checked=True)
    assert "bank_account" not in reviewed.fields
    with pytest.raises(ValueError, match="500 characters"):
        reviews.confirm_document(doc, doc_type="pan_card",
                                 fields={"pan": "AAACN4821K", "name": "x" * 501},
                                 reviewer="Reviewer", reason="Checked", original_checked=True)


@pytest.mark.parametrize("kwargs, message", [
    ({"original_checked": False}, "original PDF"),
    ({"fields": {"pan": "AAACN4821K"}}, "name"),
    ({"reviewer": " "}, "Reviewer name"),
    ({"reason": " "}, "Review reason"),
])
def test_confirmation_requires_auditable_complete_values(kwargs, message):
    doc = ParsedDoc("scan.pdf", "unknown", "", {}, [], 1)
    args = {"doc_type": "pan_card", "fields": {"pan": "AAACN4821K", "name": "Nimbus"},
            "reviewer": "Reviewer", "reason": "Checked original", "original_checked": True}
    args.update(kwargs)
    with pytest.raises(ValueError, match=message):
        reviews.confirm_document(doc, **args)


def test_duplicate_content_check_uses_hash_not_filename(run_sample, master):
    submission = load_submission(1)
    docs = parse_docs(submission)
    docs.append(replace(docs[0], filename="renamed-copy.pdf"))
    out = pipeline.run_all(submission, docs, master)
    result = next(r for r in out["results"] if r["check_id"] == "DOC_DUPLICATE_FILE")
    assert result["status"] == "warn"
    assert docs[0].sha256 == docs[-1].sha256
    assert docs[0].filename in result["evidence"]["duplicate_filenames"]
    assert "renamed-copy.pdf" in result["evidence"]["duplicate_filenames"]


def test_confirmed_document_suppresses_ai_hold_but_keeps_audit_check(run_sample, master):
    submission = load_submission(1)
    docs = parse_docs(submission)
    index = next(i for i, doc in enumerate(docs) if doc.doc_type == "pan_card")
    local = docs[index]
    uncertain = replace(local, doc_type="unknown", fields={},
                        ai_review={"needs_review": True, "document_type": "pan_card",
                                   "fields": dict(local.fields), "review_reason": "Scan-only candidate."})
    reviewed = reviews.confirm_document(uncertain, doc_type="pan_card", fields=local.fields,
                                        reviewer="Reviewer", reason="Compared the printed fields to the scan.",
                                        original_checked=True)
    docs[index] = reviewed
    outcome = pipeline.run_all(submission, docs, master)
    ids = {result["check_id"] for result in outcome["results"]}
    assert "DOC_AI_REVIEW" not in ids and "DOC_ANALYST_REVIEW" in ids
    assert reviewed.ai_review["needs_review"] is True


def test_similar_vendor_name_routes_to_review_without_rejecting(master):
    sub = load_submission(1)
    extended_master = pd.concat([master, pd.DataFrame([{
        "vendor_id": "V-9999", "legal_name": "Nimbus Logistix Private Limited", "pan": "AAACZ7777H",
        "gstin": "29AAACZ7777H1ZB", "bank_account": "999888777666", "ifsc": "HDFC0000540",
        "status": "Active",
    }])], ignore_index=True)
    out = pipeline.run_all(sub, parse_docs(sub), extended_master)
    result = next(r for r in out["results"] if r["check_id"] == "DUP_NAME_REVIEW")
    assert result["status"] == "fail" and result["severity"] == "review"
    assert out["decision"]["status"] == "PENDING"
    assert "not proof of identity" in result["internal_note"]
    assert result["vendor_ask"] == ""


def test_reviewer_event_is_append_only_and_keeps_original_outcome(run_sample):
    out = run_sample(1)
    saved = store.save(out["submission"]["submission_ref"], out["submission"], [], out["results"],
                       out["decision"], {"body": "original"}, "original note", 1.0)
    original = store.get_run(saved["run_id"])
    revised = {**original["decision"], "status": "PENDING", "queue": "Compliance review",
               "risk_score": 35, "headline": "Needs review"}
    payload = {"created_at": "2026-11-12T12:00:00", "documents": original["documents"],
               "results": original["results"], "decision": revised, "email": {"body": "review"},
               "internal_note": "reviewed"}
    event_id = store.add_analyst_review(saved["run_id"], "Reviewer", "Confirmed PDF", payload)
    current = store.get_run(saved["run_id"])
    assert event_id > 0 and current["version"] == 1
    assert current["status"] == "PENDING" and current["original_decision"]["status"] == "APPROVED"
    assert current["decision"]["status"] == "PENDING"
    assert len(current["review_history"]) == 1
    assert store.latest(out["submission"]["submission_ref"])["version"] == 1
