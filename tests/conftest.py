"""Shared fixtures: sample loading, pipeline helpers, and an isolated audit DB per test."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import documents, pipeline, store  # noqa: E402

SAMPLES = ROOT / "samples"
SCENARIOS = {
    1: "01_happy_path", 2: "02_edge_cross_field", 3: "03_edge_third_party_bank",
    4: "04_edge_wrong_documents", 5: "05_edge_resubmission_bank_swap", 6: "06_bonus_proprietorship",
}


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Never touch data/runs.db from a test."""
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "runs.db")


@pytest.fixture(scope="session")
def master() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data" / "vendor_master.csv", dtype=str)


def load_submission(n: int) -> dict:
    return json.loads((SAMPLES / f"{SCENARIOS[n]}.json").read_text(encoding="utf-8"))["submission"]


def parse_docs(sub: dict) -> list[documents.ParsedDoc]:
    return [documents.parse(f, (SAMPLES / "docs" / f).read_bytes()) for f in sub["documents"]]


def set_path(sub: dict, path: str, value) -> None:
    cur = sub
    *parents, leaf = path.split(".")
    for part in parents:
        cur = cur.setdefault(part, {})
    cur[leaf] = value


def as_previous(sub: dict, out: dict, version: int = 1) -> dict:
    """Shape a finished run the way the pipeline expects `previous`."""
    return {"submission": pipeline.normalise_submission(sub), "results": out["results"], "version": version}


@pytest.fixture
def run_sample(master):
    def _run(n: int, previous: dict | None = None, changes: dict | None = None, docs=None):
        sub = copy.deepcopy(load_submission(n))
        for path, value in (changes or {}).items():
            set_path(sub, path, value)
        parsed = parse_docs(sub) if docs is None else docs
        out = pipeline.run_all(sub, parsed, master, previous)
        out["submission"] = sub
        return out
    return _run


def by_id(out: dict, check_id: str) -> dict | None:
    return next((r for r in out["results"] if r["check_id"] == check_id), None)


def failed_ids(out: dict) -> list[str]:
    return [r["check_id"] for r in out["results"] if r["status"] == "fail"]


def warned_ids(out: dict) -> list[str]:
    return [r["check_id"] for r in out["results"] if r["status"] == "warn"]
