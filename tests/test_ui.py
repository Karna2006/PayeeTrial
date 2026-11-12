"""D · UI smoke tests with Streamlit's headless AppTest: the app boots, the 6 scenarios give the
right decision through the real UI code path, and the resubmission / reset flows work."""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT, SCENARIOS
from engine import store
from ui import metrics, state

EXPECTED = {1: ("APPROVED", "Ready for vendor master"), 2: ("PENDING", "Awaiting vendor"),
            3: ("REJECTED", "Closed: rejected"), 4: ("PENDING", "Awaiting vendor"),
            6: ("APPROVED", "Ready for vendor master")}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr("engine.messages.ollama_available", lambda timeout=0.6: False)
    state.load_master.clear()
    state.scenarios.clear()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.session_state["ui_pacing"] = False
    at.run()
    assert not at.exception
    return at


def run_scenario(at: AppTest, n: int) -> AppTest:
    at.selectbox(key="ui_scenario").set_value(SCENARIOS[n]).run()
    at.button(key="btn_load").click().run()
    at.button(key="btn_run").click().run()
    assert not at.exception, at.exception
    return at


def page_text(at: AppTest) -> str:
    return " ".join(str(el.value) for el in [*at.markdown, *at.caption, *at.info, *at.code])


def goto(at: AppTest, page: str) -> AppTest:
    at.sidebar.radio(key="page").set_value(page).run()
    assert not at.exception, at.exception
    return at


def test_d1_every_page_boots_empty(app):
    assert "Run a vendor submission through 26 checks across 5 stages." in page_text(app)
    for page in ("Dashboard", "Run detail", "Outbox"):
        goto(app, page)
        assert "No runs yet. Go to Submit & Verify and load a demo scenario." in page_text(app)


def test_d1b_loading_a_scenario_fills_every_field(app):
    app.selectbox(key="ui_scenario").set_value(SCENARIOS[6]).run()
    app.button(key="btn_load").click().run()
    ss = app.session_state
    assert ss["f_legal_name"] == "Meera Iyer" and ss["f_entity_type"] == "Proprietorship"
    assert ss["f_proprietor_name"] == "Meera Iyer" and ss["f_address.state"] == "Kerala"
    assert ss["f_bank.ifsc"] == "FDRL0001021" and ss["ui_ref"] == "VS-2026-106"
    assert len(ss["ui_attached"]) == 3
    assert any(t.label == "Proprietor's full name" for t in app.text_input)


@pytest.mark.parametrize("n", sorted(EXPECTED))
def test_d2_scenarios_through_the_ui(app, n):
    run_scenario(app, n)
    saved = store.all_runs()
    assert len(saved) == 1 and (saved[0]["status"], saved[0]["queue"]) == EXPECTED[n]
    record = app.session_state["last_run"]
    assert record["decision"]["status"] == EXPECTED[n][0] and record["version"] == 1
    assert EXPECTED[n][1] in page_text(app)
    assert len(app.status) == 5  # one live panel per stage


def test_d3_resubmission_flow(app):
    run_scenario(app, 2)
    app.selectbox(key="ui_scenario").set_value(SCENARIOS[5]).run()
    app.button(key="btn_load").click().run()
    assert "Resubmission detected: this will be v2 of VS-2026-102 (v1 was PENDING · Awaiting vendor)" in page_text(app)
    app.button(key="btn_run").click().run()
    assert not app.exception
    record = app.session_state["last_run"]
    assert (record["version"], record["decision"]["queue"]) == (2, "Compliance review")
    assert record["decision"]["fraud_signals"] == ["RESUB_BANK_CHANGE"]
    assert any("Changes vs previous" in t.label for t in app.tabs)
    assert "V-1042" not in record["email"]["body"] and record["email"]["asks"] == []

    queue = metrics.work_queue(store.all_runs())
    assert [r["version"] for r in queue["Compliance review"]] == [2] and queue["Awaiting vendor"] == []

    for page in ("Dashboard", "Run detail", "Outbox"):
        goto(app, page)
    goto(app, "Submit & Verify")
    assert app.session_state["f_gstin"] == "27AAACR7781P1ZK"  # form survives navigation


def test_d3b_blank_form_runs_without_crashing(app):
    app.button(key="btn_blank").click().run()
    app.button(key="btn_run").click().run()
    assert not app.exception
    record = app.session_state["last_run"]
    assert record["decision"]["queue"] == "Awaiting vendor" and record["ref"].endswith("-201")


def test_d3c_resubmit_button_prefills_form(app):
    run_scenario(app, 2)
    goto(app, "Dashboard")
    run_id = store.all_runs()[0]["run_id"]
    app.button(key=f"q_resub_{run_id}").click().run()
    assert not app.exception
    ss = app.session_state
    assert ss["page"] == "Submit & Verify" and ss["ui_ref"] == "VS-2026-102"
    assert ss["f_pan"] == "AAACR7731P" and ss["ui_attached"] == []


def test_d4_reset_demo_data(app):
    run_scenario(app, 1)
    goto(app, "Dashboard")
    assert "No runs yet" not in page_text(app)
    app.sidebar.checkbox(key="ui_confirm_reset").check().run()
    app.sidebar.button(key="btn_reset").click().run()
    assert not app.exception and store.all_runs() == []
    assert "No runs yet. Go to Submit & Verify and load a demo scenario." in page_text(app)
