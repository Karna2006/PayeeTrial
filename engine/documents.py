"""Document intake: bound PDF processing and extract only reviewable evidence."""
from __future__ import annotations

import io
import hashlib
import re
from dataclasses import dataclass, field

from pypdf import PdfReader

DOC_TYPES = {
    "gst_certificate": "GST Registration Certificate",
    "pan_card": "PAN Card",
    "cancelled_cheque": "Cancelled Cheque",
    "unknown": "Unrecognised document",
}

# Limits keep the synchronous demo responsive. A production service should also
# isolate PDF parsing in a resource-limited worker and scan uploads for malware.
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 40
MAX_EXTRACTED_CHARS = 300_000
MAX_DOCUMENTS_PER_SUBMISSION = 6

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
    warnings: list[str] = field(default_factory=list)
    page_count: int | None = None
    ai_review: dict | None = None
    page_texts: list[str] = field(default_factory=list)
    sha256: str = ""
    file_size: int = 0
    analyst_review: dict | None = None

    @property
    def label(self) -> str:
        return DOC_TYPES.get(self.doc_type, self.doc_type)


def extract_text(data: bytes) -> str:
    text, _, _, _ = _extract_text(data)
    return text


def _extract_text(data: bytes) -> tuple[str, list[str], int | None, list[str]]:
    """Return explicit intake warnings instead of silently treating failures as empty PDFs."""
    if len(data) > MAX_DOCUMENT_BYTES:
        return "", [f"File exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB limit."], None, []
    if b"%PDF-" not in data[:1024]:
        return "", ["File does not have a valid PDF header."], None, []
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return "", ["PDF is encrypted and cannot be read without a password."], None, []
        page_count = len(reader.pages)
        if page_count > MAX_PDF_PAGES:
            return "", [f"PDF has {page_count} pages; the limit is {MAX_PDF_PAGES}."], page_count, []
        chunks: list[str] = []
        page_texts: list[str] = []
        warnings: list[str] = []
        total = 0
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                chunk = page.extract_text() or ""
            except Exception:
                warnings.append(f"Text extraction failed on page {page_number}.")
                chunks.append("")
                page_texts.append("")
                continue
            remaining = MAX_EXTRACTED_CHARS - total
            if len(chunk) > remaining:
                bounded_chunk = chunk[:remaining]
                chunks.append(bounded_chunk)
                page_texts.append(bounded_chunk)
                warnings.append(f"Extracted text was capped at {MAX_EXTRACTED_CHARS:,} characters.")
                chunks.extend([""] * (page_count - page_number))
                page_texts.extend([""] * (page_count - page_number))
                break
            chunks.append(chunk)
            page_texts.append(chunk)
            total += len(chunk)
        text = "\n".join(chunks)
        if not text.strip() and not warnings:
            warnings.append("No selectable text found; this may be a scanned PDF and needs OCR.")
        return text, warnings, page_count, page_texts
    except Exception:
        return "", ["PDF could not be read; it may be corrupt or unsupported."], None, []


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
    text, warnings, page_count, page_texts = _extract_text(data)
    doc_type = classify(text)
    return ParsedDoc(filename=filename, doc_type=doc_type, text=text,
                     fields=parse_fields(doc_type, text), warnings=warnings, page_count=page_count,
                     page_texts=page_texts, sha256=hashlib.sha256(data).hexdigest(), file_size=len(data))
