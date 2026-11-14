"""Audited analyst confirmation for uncertain document extraction."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .documents import ParsedDoc

REQUIRED_FIELDS = {
    "gst_certificate": ("gstin", "legal_name", "status"),
    "pan_card": ("pan", "name"),
    "cancelled_cheque": ("ifsc", "account_number", "account_holder"),
}
ALLOWED_FIELDS = {
    "gst_certificate": frozenset({"gstin", "legal_name", "trade_name", "address", "status"}),
    "pan_card": frozenset({"pan", "name"}),
    "cancelled_cheque": frozenset({"ifsc", "account_number", "account_holder", "bank_name"}),
}


def confirm_document(doc: ParsedDoc, *, doc_type: str, fields: dict[str, str], reviewer: str,
                     reason: str, original_checked: bool, created_at: str | None = None) -> ParsedDoc:
    """Return a new reviewed document; never mutate or replace the original AI candidate."""
    reviewer, reason = reviewer.strip(), reason.strip()
    if doc_type not in REQUIRED_FIELDS:
        raise ValueError("Select one of the supported document types.")
    if not reviewer or len(reviewer) > 120:
        raise ValueError("Reviewer name is required and must be at most 120 characters.")
    if not reason or len(reason) > 1000:
        raise ValueError("Review reason is required and must be at most 1,000 characters.")
    if not original_checked:
        raise ValueError("Confirm that you checked the original PDF before accepting its values.")
    accepted = {}
    for key, value in fields.items():
        if key not in ALLOWED_FIELDS[doc_type]:
            continue
        clean = str(value).strip()
        if len(clean) > 500:
            raise ValueError(f"{key} must be at most 500 characters.")
        if clean:
            accepted[str(key)] = clean
    missing = [key for key in REQUIRED_FIELDS[doc_type] if not accepted.get(key)]
    if missing:
        raise ValueError("Fill the required document fields: " + ", ".join(missing))
    if doc_type == "pan_card":
        accepted["pan"] = accepted["pan"].upper().replace(" ", "")
    elif doc_type == "gst_certificate":
        accepted["gstin"] = accepted["gstin"].upper().replace(" ", "")
    elif doc_type == "cancelled_cheque":
        accepted["ifsc"] = accepted["ifsc"].upper().replace(" ", "")
        accepted["account_number"] = accepted["account_number"].replace(" ", "")
    old_fields = dict(doc.fields)
    audit = {
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
        "original_checked": True,
        "original_doc_type": doc.doc_type,
        "original_fields": old_fields,
        "accepted_doc_type": doc_type,
        "accepted_fields": accepted,
        "action": "confirmed" if doc.doc_type == doc_type and old_fields == accepted else "corrected",
    }
    return replace(doc, doc_type=doc_type, fields=accepted, analyst_review=audit)
