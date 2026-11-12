"""Reusable view pieces. Pure presentation: every rule and number comes from engine/."""
from __future__ import annotations

from html import escape
from typing import Iterator

import pandas as pd
import streamlit as st

from engine import pipeline
from engine.documents import DOC_TYPES

ICON = {"pass": "✅", "fail": "❌", "warn": "⚠️", "info": "ℹ️"}
STATUS_ICON = {"APPROVED": "✅", "PENDING": "⏳", "REJECTED": "❌"}
STATUS_COLOR = {"APPROVED": "#059669", "PENDING": "#B45309", "REJECTED": "#B91C1C"}
# Only used to point out a filename that disagrees with the content; never used to classify.
FILENAME_HINTS = [("cheque", "cancelled_cheque", "a cheque"), ("pan", "pan_card", "a PAN card"),
                  ("gst", "gst_certificate", "a GST certificate")]

CSS = """
<style>
.block-container {padding-top: 2.4rem; max-width: 1280px;}
h1 {font-size: 28px !important; font-weight: 600 !important; padding-bottom: 0 !important;}
h3 {font-size: 18px !important; font-weight: 600 !important;}
.vg-pill {display: inline-block; padding: 3px 12px; border-radius: 999px; font-size: 12px; font-weight: 600;
          text-transform: uppercase; letter-spacing: 0.04em;}
.vg-approved {color: #059669; background: #ECFDF5;}
.vg-pending {color: #B45309; background: #FFFBEB;}
.vg-rejected {color: #B91C1C; background: #FEF2F2;}
.vg-queue {margin-left: 10px; color: #6B7280; font-size: 15px;}
.vg-headline {font-size: 18px; font-weight: 600; color: #111827; margin: 4px 0 6px;}
.vg-tag {display: inline-block; font-family: monospace; font-size: 12px; color: #B91C1C; background: #FEF2F2;
         border: 1px solid #FECACA; border-radius: 6px; padding: 1px 8px; margin-left: 6px;}
.vg-chip {display: inline-block; font-size: 13px; color: #111827; background: #F6F7F9; border: 1px solid #E5E7EB;
          border-radius: 8px; padding: 4px 10px; margin: 0 6px 6px 0;}
.vg-chip.bad {color: #B91C1C; background: #FEF2F2; border-color: #FECACA;}
.vg-banner {color: #1D4ED8; background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 12px;
            padding: 10px 16px; margin: 4px 0 12px; font-size: 15px;}
.vg-muted {color: #6B7280; font-size: 13px;}
.vg-section {font-size: 12px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
             color: #6B7280; margin: 10px 0 2px;}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def section(label: str) -> None:
    st.markdown(f"<div class='vg-section'>{escape(label)}</div>", unsafe_allow_html=True)


def md_safe(text: str) -> str:
    """Vendor-typed text goes into markdown; stop '$' and '*' from being read as formatting."""
    return str(text).replace("$", "\\$").replace("*", "\\*").replace("_", "\\_")


def status_pill(status: str) -> str:
    return f"<span class='vg-pill vg-{escape(status.lower())}'>{STATUS_ICON.get(status, '')} {escape(status)}</span>"


def banner(text: str) -> None:
    st.markdown(f"<div class='vg-banner'>{escape(text)}</div>", unsafe_allow_html=True)


def risk_bar(score: int, level: str) -> None:
    st.progress(min(max(score, 0), 100) / 100, text=f"Risk **{score}** / 100 · {level}")


def check_row(result: dict) -> None:
    st.markdown(f"{ICON.get(result['status'], '•')} **{md_safe(result['name'])}**: {md_safe(result['detail'])}")
    if result["status"] in ("fail", "warn"):
        if result.get("vendor_ask"):
            ask = result["vendor_ask"]
            st.caption(f"→ asks vendor: {md_safe(ask if len(ask) <= 160 else ask[:157] + '…')}")
        if result.get("internal_note"):
            st.caption(f"→ internal: {md_safe(result['internal_note'])}")


def stage_summary(results: list[dict]) -> tuple[str, str, str]:
    """(icon, 'n passed · n failed', st.status state) for one stage."""
    n = {s: sum(r["status"] == s for r in results) for s in ("pass", "fail", "warn", "info")}
    parts = []
    if n["fail"]:
        parts.append(f"{n['fail']} failed")
    if n["warn"]:
        parts.append(f"{n['warn']} warning{'s' if n['warn'] > 1 else ''}")
    if n["pass"]:
        parts.append(f"{n['pass']} passed")
    if n["info"]:
        parts.append(f"{n['info']} note{'s' if n['info'] > 1 else ''}")
    text = " · ".join(parts) or "no checks applied"
    if n["fail"]:
        return ICON["fail"], text, "error"
    return (ICON["warn"] if n["warn"] else ICON["pass"]), text, "complete"


def render_stages(stream: Iterator[tuple[str, str, list[dict], float | None]]) -> None:
    """One st.status panel per stage. With a live pipeline generator each panel shows 'running'
    until its stage yields; with stored stages it renders instantly. Same look either way."""
    for i, (_, label) in enumerate(pipeline.STAGES, 1):
        box = st.status(f"⏳ {i} · {label}…", expanded=False)
        try:
            _, _, results, ms = next(stream)
        except StopIteration:
            box.update(label=f"{i} · {label}: not run", state="complete")
            continue
        with box:
            for r in results:
                check_row(r)
            if not results:
                st.caption("No checks applied at this stage.")
        icon, text, state = stage_summary(results)
        timing = f" · {ms:.0f} ms" if ms is not None else ""
        box.update(label=f"{icon} {i} · {label}: {text}{timing}", state=state,
                   expanded=any(r["status"] in ("fail", "warn") for r in results))


def doc_chips(docs: list[dict]) -> None:
    """filename → detected type. Red when unrecognised or when the filename suggests another type."""
    if not docs:
        st.markdown("<span class='vg-chip bad'>No documents attached</span>", unsafe_allow_html=True)
        return
    chips = []
    for d in docs:
        label = DOC_TYPES.get(d["doc_type"], d["doc_type"])
        name = d["filename"].lower()
        hint = next((h for h in FILENAME_HINTS if h[0] in name), None)
        if d["doc_type"] == "unknown":
            chips.append(f"<span class='vg-chip bad'>❌ {escape(d['filename'])} → {escape(label)}</span>")
        elif hint and hint[1] != d["doc_type"]:
            chips.append(f"<span class='vg-chip bad'>⚠️ {escape(d['filename'])} → named like {hint[2]}, "
                         f"reads as {escape(label)}</span>")
        else:
            chips.append(f"<span class='vg-chip'>{escape(d['filename'])} → {escape(label)} ✓</span>")
    st.markdown("<b>Documents read:</b> " + "".join(chips), unsafe_allow_html=True)


def decision_card(decision: dict, meta: dict) -> None:
    with st.container(border=True):
        left, right = st.columns([3, 2], vertical_alignment="center")
        left.markdown(f"{status_pill(decision['status'])}<span class='vg-queue'>{escape(decision['queue'])}</span>",
                      unsafe_allow_html=True)
        with right:
            risk_bar(decision["risk_score"], decision["risk_level"])
        st.markdown(f"<div class='vg-headline'>{escape(decision['headline'])}</div>", unsafe_allow_html=True)
        if decision.get("fraud_signals"):
            tags = "".join(f"<span class='vg-tag'>{escape(s)}</span>" for s in decision["fraud_signals"])
            st.markdown(f"🚩 <b>Fraud signals:</b>{tags}", unsafe_allow_html=True)
        foot = [f"{decision['n_pass']} passed", f"{decision['n_fail']} failed", f"{decision['n_warn']} warnings"]
        if meta.get("duration_ms") is not None:
            foot.append(f"{meta['duration_ms']:.0f} ms")
        foot += [f"run #{meta['run_id']}", f"`{meta['ref']}` v{meta['version']}"]
        if meta.get("created_at"):
            foot.append(str(meta["created_at"]).replace("T", " "))
        st.caption(" · ".join(foot))


def email_view(email: dict) -> None:
    st.markdown(f"**To:** `{email.get('to') or '(no contact email on the form)'}`")
    st.markdown(f"**Subject:** {md_safe(email['subject'])}")
    st.code(email["body"], language=None, wrap_lines=True)
    st.caption(f"Generated by: {email.get('polished_by', 'template')}")


def diff_table(prev_sub: dict, sub: dict, prev_results: list[dict]) -> None:
    rows = pipeline.classify_changes(prev_sub, sub, prev_results)
    if not rows:
        st.caption("No form fields changed compared with the previous version.")
        return
    frame = pd.DataFrame([{"Field": r["field"], "Previous": r["before"] or "(blank)", "Now": r["after"] or "(blank)",
                           "Requested?": "✅ requested" if r["requested"] else "⚠️ unrequested"} for r in rows])
    st.dataframe(frame, hide_index=True, width="stretch")
    st.caption("Requested = the previous review failed a check on that field. "
               "Unrequested changes are what a reviewer should look at first.")


def kv_table(pairs: dict) -> None:
    frame = pd.DataFrame([{"Field": k, "Value": str(v)} for k, v in pairs.items() if str(v).strip()])
    if frame.empty:
        st.caption("Nothing extracted.")
    else:
        st.dataframe(frame, hide_index=True, width="stretch")


def run_view(record: dict, title: str = "Live run") -> None:
    section(title)
    doc_chips(record["docs"])
    render_stages(iter(record["stages"]))


def result_tabs(record: dict) -> None:
    """Vendor email · Internal note · (Changes vs previous) · Raw record."""
    prev = record.get("previous")
    names = ["📧 Vendor email", "📝 Internal note"] + (["🔀 Changes vs previous"] if prev else []) + ["🧾 Raw record"]
    tabs = dict(zip(names, st.tabs(names)))
    with tabs["📧 Vendor email"]:
        email_view(record["email"])
    with tabs["📝 Internal note"]:
        st.code(record["note"], language=None, wrap_lines=True)
        st.caption("Visible to procurement/compliance only. Never sent to the vendor.")
    if prev:
        with tabs["🔀 Changes vs previous"]:
            st.caption(f"v{record['version']} compared with v{prev['version']} of {record['ref']}")
            diff_table(prev["submission"], record["submission"], prev["results"])
    with tabs["🧾 Raw record"]:
        st.json({"submission": record["submission"], "documents": record["docs"],
                 "results": record["results"], "decision": record["decision"]}, expanded=1)


def decision_section(record: dict) -> None:
    section("Decision")
    decision_card(record["decision"], record)
    result_tabs(record)
