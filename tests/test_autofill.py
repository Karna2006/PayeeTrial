from __future__ import annotations

from conftest import load_submission, parse_docs
from engine import autofill
from engine.documents import ParsedDoc


def test_local_pdf_fields_map_to_form_without_inventing_contact_values():
    docs = parse_docs(load_submission(1))
    suggestions = autofill.suggestions_from_docs(docs)
    filled, audit = autofill.apply_suggestions({}, suggestions)
    assert filled["gstin"] == "29AAACN4821K1ZB"
    assert filled["pan"] == "AAACN4821K"
    assert filled["bank.account_number"] == "50200012345678"
    assert filled["bank.ifsc"] == "HDFC0001234"
    assert filled["address.city"] == "Bengaluru"
    assert "contact.email" not in filled and "contact.phone" not in filled
    assert all(item["status"] == "auto_filled" for item in audit)


def test_autofill_never_overwrites_existing_values_and_reports_conflicts():
    suggestions = [
        {"field": "pan", "value": "AAACN4821K", "filename": "pan.pdf", "source_field": "pan",
         "source": "PDF text", "page_number": None, "quote": "", "requires_confirmation": False},
        {"field": "gstin", "value": "29AAACN4821K1ZB", "filename": "gst-a.pdf", "source_field": "gstin",
         "source": "PDF text", "page_number": None, "quote": "", "requires_confirmation": False},
        {"field": "gstin", "value": "27AAACN4821K1ZB", "filename": "gst-b.pdf", "source_field": "gstin",
         "source": "PDF text", "page_number": None, "quote": "", "requires_confirmation": False},
    ]
    filled, audit = autofill.apply_suggestions({"pan": "BBBBB0000B"}, suggestions)
    assert filled["pan"] == "BBBBB0000B" and "gstin" not in filled
    assert {item["field"]: item["status"] for item in audit} == {
        "pan": "existing_value_kept", "gstin": "conflict",
    }


def test_ai_ocr_suggestions_require_a_cited_quote_with_the_candidate_value():
    doc = ParsedDoc("scan.pdf", "unknown", "", {}, [], 1, ai_review={
        "document_type": "pan_card", "fields": {"pan": "AAACN4821K", "name": "Nimbus Logistics"},
        "evidence": [{"field": "pan", "page_number": 1, "quote": "PAN AAACN4821K"}],
        "needs_review": True,
    })
    suggestions = autofill.suggestions_from_docs([doc])
    assert len(suggestions) == 1
    assert suggestions[0]["field"] == "pan" and suggestions[0]["requires_confirmation"]
