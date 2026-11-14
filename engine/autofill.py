"""Source-linked, non-overwriting field suggestions from uploaded documents."""
from __future__ import annotations

import re

from .documents import ParsedDoc

TARGETS = {
    "gst_certificate": {
        "gstin": "gstin", "legal_name": "legal_name", "trade_name": "trade_name",
    },
    "pan_card": {"pan": "pan", "name": "legal_name"},
    "cancelled_cheque": {
        "ifsc": "bank.ifsc", "account_number": "bank.account_number",
        "account_holder": "bank.account_holder", "bank_name": "bank.bank_name",
    },
}


def _normal(value: str, field_name: str = "") -> str:
    if field_name in {"legal_name", "trade_name", "bank.account_holder"}:
        from .validators import normalize_name
        return normalize_name(str(value))
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _address_parts(address: str) -> dict[str, str]:
    """Split only the clear comma-delimited Indian address format; leave ambiguous forms alone."""
    parts = [part.strip() for part in str(address).split(",") if part.strip()]
    if len(parts) < 3:
        return {}
    from .validators import GST_STATE_CODES
    states = {name.casefold(): name for name in GST_STATE_CODES.values()}
    if re.fullmatch(r"[1-9]\d{5}", parts[-1]):
        if len(parts) < 4:
            return {}
        pin, raw_state, city, street_parts = parts[-1], parts[-2], parts[-3], parts[:-3]
    else:
        match = re.fullmatch(r"(.+?)\s+([1-9]\d{5})", parts[-1])
        if not match:
            return {}
        raw_state, pin, city, street_parts = match.group(1).strip(), match.group(2), parts[-2], parts[:-2]
    state = states.get(raw_state.casefold())
    if not state:
        return {}
    line1 = ", ".join(street_parts)
    if not line1 or not city:
        return {}
    return {"address.line1": line1, "address.city": city,
            "address.state": state, "address.pincode": pin}


def suggestions_from_docs(docs: list[ParsedDoc]) -> list[dict]:
    """Map locally extracted fields or evidenced AI OCR candidates to form fields."""
    suggestions: list[dict] = []
    for doc in docs:
        ai = doc.ai_review or {}
        use_ai = not doc.fields and ai.get("document_type") in TARGETS
        if use_ai:
            doc_type = ai["document_type"]
            candidate_fields = ai.get("fields") or {}
            source = "AI OCR candidate (unconfirmed)"
            evidence_by_field = {item.get("field"): item for item in ai.get("evidence", [])
                                 if isinstance(item, dict)}
        else:
            doc_type = doc.doc_type
            candidate_fields = doc.fields
            source = "PDF text"
            evidence_by_field = {}
        if doc_type not in TARGETS:
            continue
        for field_name, target in TARGETS[doc_type].items():
            value = candidate_fields.get(field_name)
            if not isinstance(value, str) or not value.strip():
                continue
            evidence = evidence_by_field.get(field_name, {})
            quote = str(evidence.get("quote", ""))
            if use_ai and (not quote or _normal(value) not in _normal(quote)):
                # Do not prefill an AI value unless its own cited evidence contains it.
                continue
            suggestions.append({
                "field": target, "value": value.strip(), "filename": doc.filename,
                "source_field": field_name, "source": source,
                "page_number": evidence.get("page_number"), "quote": quote,
                "requires_confirmation": bool(use_ai),
            })
        address_value = candidate_fields.get("address")
        address_evidence = evidence_by_field.get("address", {})
        address_quote = str(address_evidence.get("quote", ""))
        address_is_grounded = (not use_ai or
                               bool(address_quote and _normal(address_value or "") in _normal(address_quote)))
        if doc_type == "gst_certificate" and isinstance(address_value, str) and address_is_grounded:
            for target, value in _address_parts(address_value).items():
                suggestions.append({"field": target, "value": value, "filename": doc.filename,
                                    "source_field": "address", "source": source,
                                    "page_number": address_evidence.get("page_number"),
                                    "quote": address_quote or address_value,
                                    "requires_confirmation": bool(use_ai)})
    return suggestions


def apply_suggestions(values: dict[str, str], suggestions: list[dict]) -> tuple[dict[str, str], list[dict]]:
    """Fill empty values only; retain conflicts and source records for display/audit."""
    updated = dict(values)
    audit = []
    fields = dict.fromkeys(item.get("field") for item in suggestions)
    for field_name in fields:
        candidates = [item for item in suggestions if item.get("field") == field_name]
        distinct = {_normal(item.get("value", ""), field_name) for item in candidates if item.get("value")}
        current = str(updated.get(field_name) or "").strip()
        if len(distinct) > 1:
            status = "conflict"
        elif not current:
            updated[field_name] = candidates[0]["value"]
            status = "auto_filled"
        elif _normal(current, field_name) in distinct:
            status = "already_matches"
        else:
            status = "existing_value_kept"
        audit.append({"field": field_name, "status": status, "suggestions": candidates,
                      "final_value": updated.get(field_name, "")})
    return updated, audit
