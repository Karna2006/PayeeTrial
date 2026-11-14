"""Dashboard: KPIs, charts, work queue, run history."""
from __future__ import annotations

import streamlit as st

from engine import store
from ui import components as C
from ui import metrics, state


def run_label(r: dict) -> str:
    return f"#{r['run_id']} · {r['submission_ref']} v{r['version']} · {r['vendor_name'] or '(blank)'} · {r['status']}"


def _kpis(runs: list[dict]) -> None:
    k = metrics.kpis(runs)
    tiles = st.columns(6)
    tiles[0].metric("Runs", k["total"], border=True)
    tiles[1].metric("Approved", k["approved"], f"{k['approval_rate']}% of runs", delta_color="off",
                    delta_arrow="off", border=True)
    tiles[2].metric("Pending", k["pending"], border=True)
    tiles[3].metric("Rejected", k["rejected"], border=True)
    tiles[4].metric("Avg rule score", k["avg_rule_score"], help="Weighted rule findings, not a calibrated probability.", border=True)
    tiles[5].metric("Avg time", f"{k['avg_ms']:.0f} ms", border=True)


def _charts(runs: list[dict]) -> None:
    left, right = st.columns(2)
    with left, st.container(border=True):
        C.section("Status split")
        st.bar_chart(metrics.status_split(runs), y=metrics.STATUSES, height=260, y_label="runs",
                     color=[C.STATUS_COLOR[s] for s in metrics.STATUSES])
    with right, st.container(border=True):
        C.section("Top failing checks (all runs)")
        top = metrics.top_failing(runs)
        if top.empty:
            st.caption("No failed checks yet.")
        else:
            st.bar_chart(top, x="check", y="failures", horizontal=True, height=260,
                         color=C.STATUS_COLOR["REJECTED"],
                         sort="-failures", x_label="failed runs", y_label="")


def _work_queue(runs: list[dict]) -> None:
    st.subheader("Work queue")
    st.caption("Latest version of each submission that is still pending, grouped by who acts next.")
    queues = metrics.work_queue(runs)
    if not any(queues.values()):
        st.caption("Nothing is waiting on anyone.")
        return
    for queue, rows in queues.items():
        st.markdown(f"**{queue} ({len(rows)})**")
        for r in rows:
            c = st.columns([1.3, 2.6, 0.5, 0.8, 4.2, 0.9, 1.2], vertical_alignment="center")
            c[0].markdown(f"`{r['submission_ref']}`")
            c[1].markdown(C.md_safe(r["vendor_name"] or "(blank)"))
            c[2].markdown(f"v{r['version']}")
            c[3].markdown(f"rule {r['risk_score']}")
            c[4].caption(C.md_safe(r["headline"]))
            c[5].button("Open", key=f"q_open_{r['run_id']}", on_click=state.cb_goto,
                        args=("Run detail", r["run_id"]), width="stretch")
            c[6].button("Resubmit", key=f"q_resub_{r['run_id']}", on_click=state.cb_resubmit,
                        args=(r["run_id"],), width="stretch")


def _history(runs: list[dict]) -> None:
    st.subheader("Run history")
    f1, f2 = st.columns([2, 3])
    statuses = f1.multiselect("Status", metrics.STATUSES, key="ui_hist_status", placeholder="All statuses")
    search = f2.text_input("Search vendor or reference", key="ui_hist_search")
    frame = metrics.history_frame(runs, statuses, search)
    frame["Status"] = frame["Status"].map(lambda s: f"{C.STATUS_ICON.get(s, '')} {s}")
    st.dataframe(frame, hide_index=True, width="stretch", column_config={
        "Rule score": st.column_config.ProgressColumn("Rule score", min_value=0, max_value=100, format="%d"),
        "Headline": st.column_config.TextColumn("Headline", width="large")})
    shown = [r for r in runs if r["run_id"] in set(frame["#"])]
    if shown:
        pick, go = st.columns([5, 1], vertical_alignment="bottom")
        by_id = {r["run_id"]: r for r in shown}
        run_id = pick.selectbox("Open run", list(by_id), key="ui_hist_open", format_func=lambda i: run_label(by_id[i]))
        go.button("Open", key="btn_hist_open", on_click=state.cb_goto, args=("Run detail", run_id), width="stretch")


def render() -> None:
    head, refresh = st.columns([6, 1], vertical_alignment="bottom")
    head.title("Dashboard")
    refresh.button("↻ Refresh", key="btn_refresh", width="stretch")
    runs = store.all_runs()
    if not runs:
        st.info("No runs yet. Go to Submit & Verify and load a demo scenario.")
        st.button("Go to Submit & Verify", key="btn_empty_go", type="primary",
                  on_click=state.cb_goto, args=("Submit & Verify",))
        return
    _kpis(runs)
    _work_queue(runs)
    _charts(runs)
    _history(runs)
