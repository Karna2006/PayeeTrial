"""Session-state plumbing shared by the pages: form fields, navigation callbacks, run records.

Kept apart from the pages so every button callback and every page reads/writes state the same way.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from engine import pipeline, store
from engine import validators as V
from engine import autofill

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
SAMPLE_DOCS = SAMPLES / "docs"

PAGES = ["Submit & Verify", "Dashboard", "Run detail", "Outbox"]
ENTITY_TYPES = list(V.ENTITY_EXPECTED_PAN_TYPE)
STATES = sorted(V.GST_STATE_CODES.values())

# Every form field as a dot path into the Submission (Data Schema §1). Widget key = "f_" + path.
FIELD_PATHS = [
    "legal_name", "trade_name", "entity_type", "proprietor_name", "pan", "gstin",
    "address.line1", "address.city", "address.state", "address.pincode",
    "contact.name", "contact.email", "contact.phone", "website",
    "bank.account_holder", "bank.account_number", "bank.ifsc", "bank.bank_name",
]
REQUIRED_FORM_FIELDS = [
    ("legal_name", "Legal name"), ("entity_type", "Entity type"), ("pan", "PAN"), ("gstin", "GSTIN"),
    ("address.line1", "Address line 1"), ("address.city", "City"), ("address.state", "State"),
    ("address.pincode", "PIN code"), ("contact.name", "Contact name"),
    ("contact.email", "Email"), ("contact.phone", "Phone"),
    ("bank.account_holder", "Account holder name"), ("bank.account_number", "Account number"),
    ("bank.ifsc", "IFSC"), ("bank.bank_name", "Bank name"),
]
DOCUMENT_SLOTS = [
    ("gst_certificate", "GST registration certificate"),
    ("pan_card", "PAN card"),
    ("cancelled_cheque", "Cancelled cheque"),
]
MANUAL_REF_START = 200  # manual refs start at 201, clear of the demo scenarios (101-106)


def fkey(path: str) -> str:
    return f"f_{path}"


def missing_required_fields(values) -> list[str]:
    """Let the UI block an empty run while leaving invalid-but-present values to the rules."""
    missing = [label for path, label in REQUIRED_FORM_FIELDS if not str(values.get(fkey(path)) or "").strip()]
    if values.get(fkey("entity_type")) == "Proprietorship" and not str(values.get(fkey("proprietor_name")) or "").strip():
        missing.append("Proprietor's full name")
    return missing


def attached_sample_slots(names: list[str]) -> dict[str, list[str]]:
    """Map synthetic sample names to their form slots; the engine still classifies by PDF content."""
    slots: dict[str, list[str]] = {slot: [] for slot, _ in DOCUMENT_SLOTS}
    hints = {"gst_certificate": "gst", "pan_card": "pan", "cancelled_cheque": "cheque"}
    for name in names:
        if not (SAMPLE_DOCS / name).is_file():
            continue
        lowered = name.lower()
        for slot, hint in hints.items():
            if hint in lowered:
                slots[slot].append(name)
                break
    return slots


def init() -> None:
    """Set defaults once, and keep form values alive while other pages are shown.

    Streamlit drops a widget's state when the widget isn't rendered in a run; re-assigning
    the key marks it as user state so a half-filled form survives a trip to the Dashboard.
    """
    ss = st.session_state
    for path in FIELD_PATHS:
        ss.setdefault(fkey(path), "")
    ss.setdefault("page", PAGES[0])
    ss.setdefault("ui_pacing", True)
    ss.setdefault("ui_ai_review", False)
    ss.setdefault("ui_ai_polish", False)
    ss.setdefault("ui_confirm_reset", False)
    ss.setdefault("ui_attached", [])
    ss.setdefault("review_pdf_bytes", {})
    ss.setdefault("autofill_review_cache", {})
    ss.setdefault("autofill_upload_signature", None)
    ss.setdefault("autofill_report", None)
    ss.setdefault("ui_upload_nonce", 0)
    if "ui_ref" not in ss:
        ss["ui_ref"] = new_ref()
    for key in list(ss.keys()):
        if key.startswith("f_") or key == "selected_run":
            ss[key] = ss[key]


@st.cache_data(show_spinner=False)
def load_master() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data" / "vendor_master.csv", dtype=str)


@st.cache_data(show_spinner=False)
def scenarios() -> dict[str, dict]:
    """slug -> {title, expected, submission}, in file order."""
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(SAMPLES.glob("*.json"))}


def new_ref() -> str:
    """Next unused reference for a manually entered submission."""
    used = [int(m.group(1)) for r in store.all_runs() if (m := re.search(r"-(\d+)$", r["submission_ref"]))]
    return f"VS-{datetime.now().year}-{max([MANUAL_REF_START, *used]) + 1}"


# ---------------------------------------------------------------- form ----
def fill_form(sub: dict, ref: str, attached: list[str]) -> None:
    ss = st.session_state
    for path in FIELD_PATHS:
        ss[fkey(path)] = str(pipeline.get(sub, path) or "")
    if ss[fkey("entity_type")] not in ENTITY_TYPES:
        ss[fkey("entity_type")] = ""
    if ss[fkey("address.state")] not in STATES:
        ss[fkey("address.state")] = ""
    ss["ui_ref"] = ref
    ss["ui_attached"] = list(attached)
    ss["ui_upload_nonce"] += 1  # a new key empties the file uploader
    ss.pop("last_run", None)
    ss["autofill_review_cache"] = {}
    ss["autofill_upload_signature"] = None
    ss["autofill_report"] = None
    ss.pop("autofill_pending", None)


def apply_pending_autofill() -> None:
    """Apply queued suggestions before the form widgets are created on the next rerun."""
    ss = st.session_state
    suggestions = ss.pop("autofill_pending", None)
    if suggestions is None:
        return
    errors = ss.pop("autofill_pending_errors", [])
    current = {path: str(ss.get(fkey(path)) or "") for path in FIELD_PATHS}
    updated, audit = autofill.apply_suggestions(current, suggestions)
    for path, value in updated.items():
        if path in FIELD_PATHS:
            ss[fkey(path)] = value
    ss["autofill_report"] = {"audit": audit, "suggestion_count": len(suggestions), "errors": errors}


def build_submission(uploaded_names: list[str]) -> dict:
    ss = st.session_state
    sub: dict = {"submission_ref": ss["ui_ref"]}
    for path in FIELD_PATHS:
        value = str(ss.get(fkey(path)) or "").strip()
        cur = sub
        *parents, leaf = path.split(".")
        for part in parents:
            cur = cur.setdefault(part, {})
        cur[leaf] = value
    if sub["entity_type"] != "Proprietorship":
        sub["proprietor_name"] = ""  # hidden field must not carry a stale value
    sub["documents"] = [*ss["ui_attached"], *uploaded_names]
    return sub


# ----------------------------------------------------------- callbacks ----
def cb_load_scenario(slug: str | None = None) -> None:
    slug = slug or st.session_state["ui_scenario"]
    st.session_state["ui_scenario"] = slug
    sc = scenarios()[slug]
    sub = sc["submission"]
    fill_form(sub, sub["submission_ref"], sub.get("documents", []))


def cb_new_blank() -> None:
    fill_form({}, new_ref(), [])


def cb_clear_attached() -> None:
    st.session_state["ui_attached"] = []


def cb_form_changed() -> None:
    """Remove a stale result as soon as the user edits the submission."""
    st.session_state.pop("last_run", None)


def cb_goto(page: str, run_id: int | None = None) -> None:
    st.session_state["page"] = page
    if run_id is not None:
        st.session_state["selected_run"] = run_id


def cb_resubmit(run_id: int) -> None:
    """Open the form prefilled with that version; the vendor's corrected documents get attached fresh."""
    row = store.get_run(run_id)
    if row:
        fill_form(row["submission"], row["submission_ref"], [])
        st.session_state["page"] = PAGES[0]


def cb_reset() -> None:
    store.reset()
    ss = st.session_state
    ss.pop("last_run", None)
    ss.pop("selected_run", None)
    ss.pop("review_pdf_bytes", None)
    ss["autofill_report"] = None
    ss["autofill_review_cache"] = {}
    ss["autofill_upload_signature"] = None
    ss["ui_confirm_reset"] = False
    ss["ui_ref"] = new_ref() if not ss["ui_attached"] and not ss[fkey("legal_name")] else ss["ui_ref"]
    ss["ui_flash"] = "Demo data cleared"


# -------------------------------------------------------------- records ----
def previous_of(row: dict) -> dict | None:
    """The version just before this run, shaped as the pipeline's `previous`."""
    for r in store.all_runs():
        if r["submission_ref"] == row["submission_ref"] and r["version"] == row["version"] - 1:
            return {"submission": r["submission"], "results": r["results"], "version": r["version"],
                    "status": r["status"], "queue": r["queue"]}
    return None


def record_from_row(row: dict, stage_ms: dict[str, float] | None = None) -> dict:
    """One shape for 'the run just executed' and 'a run read back from the audit log'."""
    results = row["results"] or []
    stages = [(key, label, [r for r in results if r["stage"] == key], (stage_ms or {}).get(key))
              for key, label in pipeline.STAGES]
    return {"run_id": row["run_id"], "ref": row["submission_ref"], "version": row["version"],
            "created_at": row["created_at"], "duration_ms": row["duration_ms"],
            "submission": row["submission"], "docs": row["documents"] or [], "results": results,
            "stages": stages, "decision": row["decision"], "email": row["email"],
            "note": row["internal_note"] or "", "previous": previous_of(row),
            "review_history": row.get("review_history") or [],
            "original_decision": row.get("original_decision")}
