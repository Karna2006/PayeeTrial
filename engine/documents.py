"""Document intake: read uploaded PDFs, figure out what each one actually is,
and pull out the fields we need to cross-check against the form.

Digital PDFs are read with pypdf. Scanned images would go through an OCR
step (Tesseract / PaddleOCR) before this same parser - out of scope for v1.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from pypdf import PdfReader

DOC_TYPES = {
    "gst_certificate": "GST Registration Certificate",
    "pan_card": "PAN Card",
    "cancelled_cheque": "Cancelled Cheque",
    "unknown": "Unrecognised document",
}

# Keyword fingerprints, ordered by specificity
_FINGERPRINTS = [
    ("gst_certificate", [r"REG-06", r"registration certificate", r"goods and services tax"]),
    ("cancelled_cheque", [r"cancelled", r"pay\s", r"a/c no", r"ifsc"]),
    ("pan_card", [r"permanent account number", r"income tax department"]),
]


@dataclass
class ParsedDoc:
    filename: str
    doc_type: str
    text: str
    fields: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return DOC_TYPES.get(self.doc_type, self.doc_type)


def extract_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return ""


def classify(text: str) -> str:
    low = text.lower()
    best, best_hits = "unknown", 0
    for doc_type, pats in _FINGERPRINTS:
        hits = sum(1 for p in pats if re.search(p, low, re.I))
        if hits > best_hits:
            best, best_hits = doc_type, hits
    return best if best_hits >= 2 else "unknown"


def _grab(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.I | re.M)
    return m.group(1).strip() if m else None


def parse_fields(doc_type: str, text: str) -> dict:
    f: dict = {}
    if doc_type == "gst_certificate":
        f["gstin"] = _grab(r"Registration Number\s*[:\-]?\s*([0-9]{2}[A-Z0-9]{13})", text)
        f["legal_name"] = _grab(r"Legal Name\s*[:\-]?\s*(.+)$", text)
        f["trade_name"] = _grab(r"Trade Name.*?[:\-]\s*(.+)$", text)
        f["address"] = _grab(r"Address of Principal Place of Business\s*[:\-]?\s*(.+)$", text)
        f["status"] = _grab(r"Status\s*[:\-]?\s*([A-Za-z]+)", text)
    elif doc_type == "pan_card":
        f["pan"] = _grab(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", text)
        f["name"] = _grab(r"Name\s*[:\-]?\s*(.+)$", text)
    elif doc_type == "cancelled_cheque":
        f["ifsc"] = _grab(r"IFSC\s*(?:Code)?\s*[:\-]?\s*([A-Z]{4}0[A-Z0-9]{6})", text)
        f["account_number"] = _grab(r"A/C\s*No\.?\s*[:\-]?\s*([0-9]{9,18})", text)
        f["account_holder"] = _grab(r"(?:For|Account Holder)\s*[:\-]?\s*(.+)$", text)
        f["bank_name"] = _grab(r"^(.*Bank.*)$", text)
    return {k: v for k, v in f.items() if v}


def parse(filename: str, data: bytes) -> ParsedDoc:
    text = extract_text(data)
    doc_type = classify(text)
    return ParsedDoc(filename=filename, doc_type=doc_type, text=text, fields=parse_fields(doc_type, text))
