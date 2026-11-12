"""C11 · SQLite audit trail: append-only, versioned per submission reference."""
from __future__ import annotations

from engine import messages, store


def save(out, ref=None):
    sub = out["submission"]
    email = messages.vendor_email(sub, out["decision"], out["results"])
    note = messages.internal_note(out["decision"], out["results"])
    return store.save(ref or sub["submission_ref"], sub, [{"filename": f} for f in sub["documents"]],
                      out["results"], out["decision"], email, note, 4.2)


def test_store_roundtrip_and_versions(run_sample):
    assert store.all_runs() == [] and store.latest("VS-2026-101") is None

    first = save(run_sample(1))
    second = save(run_sample(2))
    third = save(run_sample(2))
    assert (first["version"], second["version"], third["version"]) == (1, 1, 2)

    runs = store.all_runs()
    assert [r["run_id"] for r in runs] == [third["run_id"], second["run_id"], first["run_id"]]  # newest first

    latest = store.latest("VS-2026-102")
    assert latest["version"] == 2 and latest["status"] == "PENDING" and latest["queue"] == "Awaiting vendor"

    row = store.get_run(first["run_id"])
    assert row["vendor_name"] == "Nimbus Logistics Private Limited" and row["risk_score"] == 0
    assert row["submission"]["pan"] == "AAACN4821K" and isinstance(row["results"], list)
    assert row["decision"]["status"] == "APPROVED" and row["email"]["polished_by"] == "template"
    assert store.get_run(9999) is None


def test_store_is_append_only_and_resettable(run_sample):
    a = save(run_sample(1))
    b = save(run_sample(1))
    assert a["run_id"] != b["run_id"] and len(store.all_runs()) == 2  # v1 is kept, never updated
    store.reset()
    assert store.all_runs() == []
    assert save(run_sample(1))["version"] == 1
