"""SQLite audit trail. Every run is stored in full, never overwritten:
resubmissions become a new version under the same submission reference."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "runs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_ref TEXT NOT NULL,
    version       INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    vendor_name   TEXT,
    status        TEXT,
    queue         TEXT,
    risk_score    INTEGER,
    headline      TEXT,
    duration_ms   REAL,
    submission    TEXT,
    documents     TEXT,
    results       TEXT,
    decision      TEXT,
    email         TEXT,
    internal_note TEXT
);
CREATE TABLE IF NOT EXISTS analyst_reviews (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs(run_id),
    created_at    TEXT NOT NULL,
    reviewer      TEXT NOT NULL,
    reason        TEXT NOT NULL,
    payload       TEXT NOT NULL
);
"""


def conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def latest(ref: str) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM runs WHERE submission_ref=? ORDER BY version DESC LIMIT 1", (ref,)).fetchone()
    return _hydrate(row) if row else None


def save(ref: str, sub: dict, docs: list[str], results: list[dict], decision: dict, email: dict,
         note: str, duration_ms: float) -> dict:
    prev = latest(ref)
    version = (prev["version"] + 1) if prev else 1
    with conn() as c:
        cur = c.execute(
            "INSERT INTO runs (submission_ref, version, created_at, vendor_name, status, queue, risk_score, headline,"
            " duration_ms, submission, documents, results, decision, email, internal_note)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ref, version, datetime.now().isoformat(timespec="seconds"), sub.get("legal_name"), decision["status"],
             decision["queue"], decision["risk_score"], decision["headline"], duration_ms, json.dumps(sub),
             json.dumps(docs), json.dumps(results), json.dumps(decision), json.dumps(email), note))
        run_id = cur.lastrowid
    return {"run_id": run_id, "version": version}


def all_runs() -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM runs ORDER BY run_id DESC").fetchall()
    return [_hydrate(r) for r in rows]


def get_run(run_id: int) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    return _hydrate(row) if row else None


def reset():
    with conn() as c:
        c.execute("DELETE FROM analyst_reviews")
        c.execute("DELETE FROM runs")


def add_analyst_review(run_id: int, reviewer: str, reason: str, payload: dict) -> int:
    """Append an analyst event without changing the vendor submission version row."""
    created_at = payload.get("created_at") or datetime.now().isoformat(timespec="seconds")
    with conn() as c:
        cur = c.execute("INSERT INTO analyst_reviews (run_id, created_at, reviewer, reason, payload) VALUES (?,?,?,?,?)",
                        (run_id, created_at, reviewer, reason, json.dumps(payload)))
        return int(cur.lastrowid)


def _hydrate(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in ("submission", "documents", "results", "decision", "email"):
        d[k] = json.loads(d[k]) if d.get(k) else None
    with conn() as c:
        events = c.execute("SELECT * FROM analyst_reviews WHERE run_id=? ORDER BY event_id", (d["run_id"],)).fetchall()
    d["review_history"] = [{**dict(event), "payload": json.loads(event["payload"])} for event in events]
    if events:
        latest_event = d["review_history"][-1]
        payload = latest_event["payload"]
        d["original_status"] = d["status"]
        d["original_queue"] = d["queue"]
        d["original_risk_score"] = d["risk_score"]
        d["original_decision"] = d["decision"]
        d["original_documents"] = d["documents"]
        d["original_results"] = d["results"]
        d["status"] = payload["decision"]["status"]
        d["queue"] = payload["decision"]["queue"]
        d["risk_score"] = payload["decision"]["risk_score"]
        d["headline"] = payload["decision"]["headline"]
        d["decision"] = payload["decision"]
        d["documents"] = payload["documents"]
        d["results"] = payload["results"]
        d["email"] = payload["email"]
        d["internal_note"] = payload["internal_note"]
    return d
