"""D · UI smoke tests with Streamlit's headless AppTest: the app boots, the 6 scenarios give the
right decision through the real UI code path, and the resubmission / reset flows work."""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT, SCENARIOS
from engine import store
from ui import metrics, page_submit, state

EXPECTED = {1: ("APPROVED", "Ready for vendor master"), 2: ("PENDING", "Awaiting vendor"),
            3: ("REJECTED", "Closed: rejected"), 4: ("PENDING", "Awaiting vendor"),
            6: ("APPROVED", "Ready for vendor master")}


@pytest.fixture
def app(monkeypatch):
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
    assert not at.button(key="btn_run").disabled
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
    assert "Collect the evidence, cross-check the details, and keep every decision traceable." in page_text(app)
    for page in ("Dashboard", "Run detail", "Outbox"):
        goto(app, page)
        assert "No runs yet. Go to Submit & Verify and load a demo scenario." in page_text(app)


def test_autofill_is_applied_before_streamlit_form_widgets_render(app):
    app.session_state["autofill_pending"] = [{
        "field": "gstin", "value": "29AAACN4821K1ZB", "filename": "synthetic_gst_scan.pdf",
        "source_field": "gstin", "source": "AI OCR candidate (unconfirmed)",
        "page_number": 1, "quote": "Registration Number: 29AAACN4821K1ZB",
        "requires_confirmation": True,
    }]
    app.run()
    assert not app.exception, app.exception
    assert app.session_state["f_gstin"] == "29AAACN4821K1ZB"
    assert app.session_state["autofill_report"]["audit"][0]["status"] == "auto_filled"


def test_autofill_button_processes_attached_scenario_documents(app):
    app.selectbox(key="ui_scenario").set_value(SCENARIOS[1]).run()
    app.button(key="btn_load").click().run()
    assert not app.button(key="btn_autofill").disabled
    app.button(key="btn_autofill").click().run()
    assert not app.exception, app.exception
    report = app.session_state["autofill_report"]
    assert report["suggestion_count"] > 0
    assert {item["status"] for item in report["audit"]} == {"already_matches"}


def test_ui_text_escapes_html_in_user_controlled_content():
    from ui.components import md_safe
    assert "&lt;script&gt;" in md_safe("<script>alert(1)</script>")


def test_d1b_loading_a_scenario_fills_every_field(app):
    app.selectbox(key="ui_scenario").set_value(SCENARIOS[6]).run()
    app.button(key="btn_load").click().run()
    ss = app.session_state
    assert ss["f_legal_name"] == "Meera Iyer" and ss["f_entity_type"] == "Proprietorship"
    assert ss["f_proprietor_name"] == "Meera Iyer" and ss["f_address.state"] == "Kerala"
    assert ss["f_bank.ifsc"] == "FDRL0001021" and ss["ui_ref"] == "VS-2026-106"
    assert len(ss["ui_attached"]) == 3
    assert any(t.label == "Proprietor's full name *" for t in app.text_input)


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


def test_d3b_run_is_blocked_until_fields_and_document_slots_are_present(app):
    app.button(key="btn_blank").click().run()
    assert app.button(key="btn_run").disabled
    assert "Complete the required items before running verification." in page_text(app)
    assert store.all_runs() == []

    app.selectbox(key="ui_scenario").set_value(SCENARIOS[6]).run()
    app.button(key="btn_load").click().run()
    assert not app.button(key="btn_run").disabled

    app.session_state["f_proprietor_name"] = ""
    app.run()
    assert app.button(key="btn_run").disabled
    assert "Proprietor's full name" in page_text(app)

    app.session_state["f_proprietor_name"] = "Meera Iyer"
    app.run()
    app.button(key="btn_clear_attached").click().run()
    assert app.button(key="btn_run").disabled
    assert "Documents to upload" in page_text(app)


@pytest.mark.parametrize("attached,uploads,over_limit", [
    (3, 3, False), (3, 4, True), (0, 6, False), (0, 7, True), (-1, 0, True),
])
def test_d3d_submission_document_count_is_bounded(attached, uploads, over_limit):
    assert page_submit._over_document_limit(attached, uploads) is over_limit


def test_d3e_ai_rewrite_failure_keeps_template_and_reports_error(app, monkeypatch):
    app.session_state["ui_ai_polish"] = True
    monkeypatch.setattr(page_submit.provider_settings, "openrouter_key", lambda: "test-key")
    monkeypatch.setattr(page_submit.messages, "polish_with_openrouter",
                        lambda email, api_key, model: {"polished_by": "template",
                                                       "polish_error": "OpenRouter rate limit reached."})

    run_scenario(app, 1)

    email = app.session_state["last_run"]["email"]
    assert "Good news: Nimbus Logistics" in email["body"]
    assert email["polished_by"] == "template"
    assert "rate limit" in email["polish_error"]


def test_d3f_openrouter_polish_is_an_unapproved_suggestion(app, monkeypatch):
    app.session_state["ui_ai_polish"] = True
    monkeypatch.setattr(page_submit.provider_settings, "openrouter_key", lambda: "test-key")
    monkeypatch.setattr(page_submit.provider_settings, "model_name", lambda: "test/vision-model:free")
    monkeypatch.setattr(page_submit.messages, "polish_with_openrouter",
                        lambda email, api_key, model: {"body": "Polished copy with all asks preserved.",
                                                       "polished_by": "openrouter:test-model"})
    run_scenario(app, 2)
    email = app.session_state["last_run"]["email"]
    assert email["polished_by"] == "template"
    assert email["body"].startswith("Hi Rohan Kulkarni")
    assert email["polish_suggestion"] == "Polished copy with all asks preserved."


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
