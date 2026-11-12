"""PayeeTrail entry point: page config, CSS, sidebar (nav + settings), routing."""
from __future__ import annotations

import streamlit as st

from engine import messages
from ui import components as C
from ui import page_dashboard, page_outbox, page_run_detail, page_submit, state

RENDER = dict(zip(state.PAGES, (page_submit.render, page_dashboard.render,
                                page_run_detail.render, page_outbox.render)))

st.set_page_config(page_title="PayeeTrail", page_icon="🛡️", layout="wide")
C.inject_css()
state.init()


@st.cache_data(ttl=30, show_spinner=False)
def ollama_detected() -> bool:
    """Cached: the probe must not slow down every rerun when Ollama isn't installed."""
    return messages.ollama_available()


with st.sidebar:
    st.markdown("### 🛡️ PayeeTrail")
    st.caption("Trust the payee. Trace every change.")
    st.radio("Navigation", state.PAGES, key="page", label_visibility="collapsed")
    st.divider()
    with st.expander("Settings"):
        st.toggle("Demo pacing", key="ui_pacing", help="Pause 0.6 s after each stage so viewers can follow.")
        ollama = ollama_detected()
        st.toggle("Polish email with local LLM (Ollama)", key="ui_polish", disabled=not ollama)
        st.caption("🟢 Ollama detected" if ollama else "⚪ Ollama not running: template only")
        st.checkbox("Yes, delete all runs", key="ui_confirm_reset")
        st.button("Reset demo data", key="btn_reset", on_click=state.cb_reset,
                  disabled=not st.session_state["ui_confirm_reset"])
    st.caption("Rules engine v1 · 26 checks · 100% offline")

if flash := st.session_state.pop("ui_flash", None):
    st.toast(flash)

RENDER[st.session_state["page"]]()
