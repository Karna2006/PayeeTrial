"""PayeeTrail entry point: page config, CSS, sidebar (nav + settings), routing."""
from __future__ import annotations

import streamlit as st

from ui import components as C
from ui import page_dashboard, page_outbox, page_run_detail, page_submit, provider_settings, state

RENDER = dict(zip(state.PAGES, (page_submit.render, page_dashboard.render,
                                page_run_detail.render, page_outbox.render)))

st.set_page_config(page_title="PayeeTrail", layout="wide")
C.inject_css()
state.init()
st.caption("Demo workspace: synthetic data only. Runs are saved locally. No bank ownership or government registry checks.")


with st.sidebar:
    st.markdown("### PayeeTrail")
    st.caption("Trust the payee. Trace every change.")
    st.radio("Navigation", state.PAGES, key="page", label_visibility="collapsed")
    st.divider()
    with st.expander("Settings"):
        st.toggle("Demo pacing", key="ui_pacing", help="Pause 0.6 s after each stage so viewers can follow.")
        api_key = provider_settings.openrouter_key()
        st.toggle("Review documents with free AI", key="ui_ai_review", disabled=not api_key,
                  help="Sends selected PDF contents to OpenRouter for advisory classification and extraction.")
        st.toggle("Polish email with the same model", key="ui_ai_polish", disabled=not api_key,
                  help="Sends the generated email body to OpenRouter; it can include vendor names, references, and correction requests.")
        if api_key:
            st.caption(f"OpenRouter · {provider_settings.model_name()}")
            st.caption("Free endpoint: limited and may log prompts or use them to improve provider products. Use synthetic demo data only.")
            st.caption("Document review sends selected PDFs. Email polish sends the generated email body, including names, references, and requested corrections.")
        else:
            st.caption("Add OPENROUTER_API_KEY to local environment or Streamlit secrets to enable both options.")
        st.caption("AI output is advisory; rules decide outcomes and email suggestions require review.")
        st.checkbox("Yes, delete all runs", key="ui_confirm_reset")
        st.button("Reset demo data", key="btn_reset", on_click=state.cb_reset,
                  disabled=not st.session_state["ui_confirm_reset"])
    st.caption("Rules engine v1 · 27 core checks · optional AI uses one model")

if flash := st.session_state.pop("ui_flash", None):
    st.toast(flash)

RENDER[st.session_state["page"]]()
