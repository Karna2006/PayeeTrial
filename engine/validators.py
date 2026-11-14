"""Deterministic validators for Indian vendor identity + banking data.

Rules live here, not in an LLM: a checksum is either right or wrong, and we
want the same answer every time with an explanation a finance team can audit.
"""
from __future__ import annotations

import re

try:
    from rapidfuzz import fuzz

    def _ratio(a: str, b: str) -> float:
        return float(fuzz.token_sort_ratio(a, b))
except ImportError:  # graceful fallback, no hard dependency
    from difflib import SequenceMatcher

    def _ratio(a: str, b: str) -> float:
        return 100.0 * SequenceMatcher(None, " ".join(sorted(a.split())), " ".join(sorted(b.split()))).ratio()


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------
GST_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}
STATE_TO_CODE = {v.lower(): k for k, v in GST_STATE_CODES.items()}

# 4th character of a PAN encodes the holder type
PAN_HOLDER_TYPES = {
    "C": "Company", "P": "Individual", "F": "Firm / LLP", "H": "HUF", "A": "AOP",
    "T": "Trust", "B": "BOI", "L": "Local Authority", "J": "Artificial Juridical Person", "G": "Government",
}
# What PAN type each declared entity type should carry
ENTITY_EXPECTED_PAN_TYPE = {
    "Private Limited Company": "C",
    "Public Limited Company": "C",
    "LLP": "F",
    "Partnership Firm": "F",
    "Proprietorship": "P",
}

# First 4 chars of IFSC = bank. Offline subset; swap in Razorpay's open IFSC
# dataset (MIT) for branch-level lookup.
IFSC_BANKS = {
    "SBIN": "State Bank of India", "HDFC": "HDFC Bank", "ICIC": "ICICI Bank", "UTIB": "Axis Bank",
    "KKBK": "Kotak Mahindra Bank", "PUNB": "Punjab National Bank", "BARB": "Bank of Baroda",
    "CNRB": "Canara Bank", "UBIN": "Union Bank of India", "IDIB": "Indian Bank", "YESB": "Yes Bank",
    "INDB": "IndusInd Bank", "IDFB": "IDFC First Bank", "FDRL": "Federal Bank", "BKID": "Bank of India",
    "IOBA": "Indian Overseas Bank", "MAHB": "Bank of Maharashtra", "RATN": "RBL Bank",
}

FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com",
                      "rediffmail.com", "protonmail.com", "icloud.com", "live.com"}

_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
EMAIL_RE = re.compile(
    r"^[A-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Z0-9!#$%&'*+/=?^_`{|}~-]+)*@"
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}$",
    re.I,
)


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------
def clean_id(value: str | None) -> str:
    return re.sub(r"[\s\-]", "", (value or "")).upper()


def clean_phone(value: str | None) -> str:
    """Last 10 digits, so '+91 98220 12345' and '9822012345' compare equal."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())[-10:]


def gstin_checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        prod = _GST_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += prod // 36 + prod % 36
    return _GST_CHARS[(36 - total % 36) % 36]


def make_gstin(state_code: str, pan: str, entity_no: str = "1") -> str:
    body = f"{state_code}{pan}{entity_no}Z"
    return body + gstin_checksum_char(body)


def pan_valid(pan: str) -> bool:
    return bool(PAN_RE.match(pan))


def gstin_format_valid(gstin: str) -> bool:
    return bool(GSTIN_RE.match(gstin))


def gstin_checksum_valid(gstin: str) -> bool:
    return gstin_format_valid(gstin) and gstin_checksum_char(gstin[:14]) == gstin[14]


def gstin_state(gstin: str) -> str | None:
    return GST_STATE_CODES.get(gstin[:2])


def gstin_embedded_pan(gstin: str) -> str:
    return gstin[2:12]


def ifsc_valid(ifsc: str) -> bool:
    return bool(IFSC_RE.match(ifsc))


def email_valid(email: str | None) -> bool:
    value = (email or "").strip()
    return len(value) <= 254 and bool(EMAIL_RE.fullmatch(value))


def ifsc_bank(ifsc: str) -> str | None:
    return IFSC_BANKS.get(ifsc[:4])


def account_number_valid(acc: str) -> bool:
    return acc.isdigit() and 9 <= len(acc) <= 18


def hamming(a: str, b: str) -> int:
    if len(a) != len(b):
        return max(len(a), len(b))
    return sum(1 for x, y in zip(a, b) if x != y)


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------
_NAME_SUBS = [
    (r"\bm/s\.?\s*", ""), (r"&", " and "), (r"\bprivate\b", "pvt"), (r"\blimited\b", "ltd"),
    (r"\bcompany\b", "co"), (r"\bcorporation\b", "corp"), (r"\bthe\b", ""),
]


def normalize_name(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r"\b([a-z])\.(?=[a-z]\.)", r"\1", s)        # A.B.C. -> ABC
    for pat, rep in _NAME_SUBS:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b([a-z]) (?=[a-z]\b)", r"\1", s)          # "a b c" -> "abc"
    return re.sub(r"\s+", " ", s).strip()


def name_similarity(a: str, b: str) -> float:
    return round(_ratio(normalize_name(a), normalize_name(b)), 1)


def strip_suffix(name: str) -> str:
    return re.sub(r"\b(pvt|ltd|llp|co|corp|inc)\b", "", normalize_name(name)).strip()


def domain_of(email_or_url: str) -> str:
    s = (email_or_url or "").lower().strip()
    if "@" in s:
        s = s.split("@", 1)[1]
    s = re.sub(r"^https?://", "", s)
    s = s.split("/")[0]
    return s[4:] if s.startswith("www.") else s
