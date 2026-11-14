from __future__ import annotations

from engine import messages
from services import openrouter


EMAIL = {"body": "Hi there. Please correct PAN AAACN4821K. Thanks.",
         "asks": ["Please correct PAN AAACN4821K."]}
MODEL = "nvidia/nemotron-3.5-super-vl:free"


def completion(text):
    return {"choices": [{"message": {"content": text}}]}


def test_openrouter_email_polish_returns_suggestion_but_not_message_of_record(monkeypatch):
    calls = {}

    def fake_completion(**kwargs):
        calls.update(kwargs)
        return completion("Hello there. Please correct PAN AAACN4821K. Thank you.")

    monkeypatch.setattr(messages.openrouter, "chat_completion", fake_completion)
    suggestion = messages.polish_with_openrouter(EMAIL, "test-key", MODEL)
    assert suggestion["polished_by"] == f"openrouter:{MODEL}"
    assert "Please correct PAN AAACN4821K." in suggestion["body"]
    assert EMAIL["body"] != suggestion["body"]
    assert calls["model"] == MODEL
    assert "untrusted data" in calls["messages"][0]["content"]


def test_openrouter_email_polish_rejects_dropped_request(monkeypatch):
    monkeypatch.setattr(messages.openrouter, "chat_completion",
                        lambda **kwargs: completion("Please update your records."))
    suggestion = messages.polish_with_openrouter(EMAIL, "test-key", MODEL)
    assert suggestion["polished_by"] == "template"
    assert "changed or omitted" in suggestion["polish_error"]


def test_openrouter_email_polish_falls_back_on_provider_failure(monkeypatch):
    def unavailable(**kwargs):
        raise openrouter.OpenRouterError("OpenRouter free-tier rate limit reached.")
    monkeypatch.setattr(messages.openrouter, "chat_completion", unavailable)
    suggestion = messages.polish_with_openrouter(EMAIL, "test-key", MODEL)
    assert suggestion["polished_by"] == "template"
    assert "rate limit" in suggestion["polish_error"]
    assert "unchanged" in suggestion["polish_error"]
