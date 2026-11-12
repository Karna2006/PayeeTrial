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
"""


def conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute(SCHEMA)
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
        c.execute("DELETE FROM runs")


def _hydrate(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in ("submission", "documents", "results", "decision", "email"):
        d[k] = json.loads(d[k]) if d.get(k) else None
    return d
