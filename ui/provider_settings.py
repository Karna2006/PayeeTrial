"""Read optional AI provider settings without ever rendering secrets."""
from __future__ import annotations

import os

import streamlit as st

from services.document_ai import DEFAULT_MODEL


def openrouter_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    try:
        return str(st.secrets.get("OPENROUTER_API_KEY", "")).strip()
    except Exception:
        return ""


def model_name() -> str:
    return os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
