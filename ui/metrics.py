"""Dashboard numbers. Pure functions over store.all_runs() so they can be tested without Streamlit."""
from __future__ import annotations

from collections import Counter

import pandas as pd

STATUSES = ["APPROVED", "PENDING", "REJECTED"]
QUEUE_ORDER = ["Compliance review", "Awaiting vendor", "Procurement review"]


def kpis(runs: list[dict]) -> dict:
    total = len(runs)
    count = Counter(r["status"] for r in runs)
    return {"total": total, "approved": count["APPROVED"], "pending": count["PENDING"],
            "rejected": count["REJECTED"],
            "approval_rate": round(100 * count["APPROVED"] / total) if total else 0,
            "avg_rule_score": round(sum(r["risk_score"] or 0 for r in runs) / total) if total else 0,
            "avg_ms": round(sum(r["duration_ms"] or 0 for r in runs) / total, 1) if total else 0.0}


def status_split(runs: list[dict]) -> pd.DataFrame:
    """One column per status (diagonal) so each bar gets its own status colour."""
    count = Counter(r["status"] for r in runs)
    return pd.DataFrame({s: [count[s] if s == row else 0 for row in STATUSES] for s in STATUSES}, index=STATUSES)


def top_failing(runs: list[dict], n: int = 8) -> pd.DataFrame:
    count = Counter(res["check_id"] for r in runs for res in (r["results"] or []) if res["status"] == "fail")
    return pd.DataFrame(count.most_common(n), columns=["check", "failures"])


def work_queue(runs: list[dict]) -> dict[str, list[dict]]:
    """Current state of a submission = its latest version; the queue holds the PENDING ones."""
    latest: dict[str, dict] = {}
    for r in runs:
        if r["submission_ref"] not in latest or r["version"] > latest[r["submission_ref"]]["version"]:
            latest[r["submission_ref"]] = r
    pending = [r for r in latest.values() if r["status"] == "PENDING"]
    return {q: sorted((r for r in pending if r["queue"] == q), key=lambda r: -(r["risk_score"] or 0))
            for q in QUEUE_ORDER}


def history_frame(runs: list[dict], statuses: list[str] | None = None, search: str = "") -> pd.DataFrame:
    needle = search.strip().lower()
    rows = [{"#": r["run_id"], "Time": str(r["created_at"]).replace("T", " "), "Ref": r["submission_ref"],
             "v": r["version"], "Vendor": r["vendor_name"] or "(blank)", "Status": r["status"],
             "Queue": r["queue"], "Rule score": r["risk_score"], "Headline": r["headline"]}
            for r in runs
            if (not statuses or r["status"] in statuses)
            and (not needle or needle in f"{r['vendor_name']} {r['submission_ref']}".lower())]
    return pd.DataFrame(rows, columns=["#", "Time", "Ref", "v", "Vendor", "Status", "Queue", "Rule score", "Headline"])
