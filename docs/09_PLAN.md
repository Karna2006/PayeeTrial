# 09 · Build Plan (one day)

Small sequential phases. **Each phase ends with something that runs, and a git commit.** Do not start a phase until the previous one's exit check passes.

> **Head start:** `engine/` (validators, documents, pipeline, messages, store) and `scripts/make_samples.py` already exist as a **tested reference implementation**. All 6 scenarios produce their expected decisions. Phases 1–2 are therefore *verify + add tests*, not *write from scratch*. Biggest remaining work: **the UI (Phases 3–5)**.

| Phase | Time | Output | Exit check |
|---|---|---|---|
| 0 · Setup | 15 min | venv, deps, git init, first commit of docs | `pip install -r requirements.txt` OK; `git log` shows the docs commit |
| 1 · Data + engine verify | 30 min | samples generated; engine reviewed against `05_RULES_SPEC.md` | `python scripts/make_samples.py` → "Wrote 6 scenarios, 17 PDFs, 6 vendors" |
| 2 · Tests | 30 min | `tests/test_scenarios.py` (7 assertions from `06_TEST_SCENARIOS.md`) | `pytest -q` all green |
| 3 · UI skeleton + Submit form | 1.5 h | `app.py`, `ui/components.py`, `ui/page_submit.py` form + scenario loader | Loading each scenario fills every field; Run button visible |
| 4 · Live run + decision | 1.5 h | Stage-by-stage `st.status` view, doc chips, decision card, 4 tabs, save to SQLite, resubmission banner + diff tab | All 6 scenarios run in the UI with the correct decision; #5 after #2 shows v2 + diff |
| 5 · Dashboard, Run detail, Outbox, Settings | 1.5 h | 3 pages + sidebar settings + reset | KPIs and charts update; Open/Resubmit buttons work; reset clears data |
| 6 · Polish | 45 min | theme, CSS, microcopy, empty states, 1280px check | Polish checklist in `07_UI_UX_SPEC.md` §9 all ticked |
| 7 · Deploy | 30 min | GitHub public repo + Streamlit Cloud app | Live URL runs all 6 scenarios |
| 8 · Demo prep + video | 1 h | Rehearse `10_DEMO_SCRIPT.md` twice; record ≤ 5 min | Video link + app link ready to email |

**Total ≈ 8.5 h.** Buffer: cut Phase 5's Outbox page first (the email is already visible on the Submit page), then Run detail's version-history table.

---

## Phase details

### Phase 0: Setup
```bash
cd vendorguard
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
git init && git add docs/ CLAUDE.md AGENTS.md README.md requirements.txt .gitignore
git commit -m "docs: planning pack"
git add . && git commit -m "feat: reference engine + sample generator"
```

### Phase 1: Data + engine verify
- Run `python scripts/make_samples.py`.
- Read `engine/pipeline.py` alongside `05_RULES_SPEC.md`; confirm all 26 check IDs exist with the specified severities.
- Add `requested_fields_map` (Rules Spec §5 table) to `engine/pipeline.py` as `REQUESTED_BY` plus a helper `classify_changes(prev_sub, sub, prev_results) -> list[{field, before, after, requested}]`. The UI diff tab needs it.

### Phase 2: Tests
`tests/test_scenarios.py`: a fixture loads master + parses docs; helper `run_sample(name, previous=None)`. Assertions exactly as listed in `06_TEST_SCENARIOS.md` "Automated tests".

### Phase 3: UI skeleton
- `app.py` ≤ 60 lines: page config, `inject_css()`, sidebar (nav + settings), dispatch to `ui/page_*.render()`.
- `ui/page_submit.py`: scenario loader (selectbox + Load button → sets `st.session_state` field keys + `attached_docs` paths + `submission_ref`, then `st.rerun()`), form with 5 sections, file uploader.
- Build the submission dict from session state on submit.

### Phase 4: Live run + decision
- Parse docs (uploaded bytes + attached sample paths) → `ParsedDoc[]` → doc chips.
- `previous = store.latest(ref)` → `{"submission", "results", "version"}` or None; show the banner *before* the Run button when it exists.
- Iterate `pipeline.run(..., delay=0.6 if pacing else 0)`, rendering each stage in `st.status`.
- `decide()` → card → email (+ optional polish) → note → `store.save()` → toast → tabs.
- Keep the last run in `st.session_state["last_run"]` so it stays visible after reruns.

### Phase 5: Other pages
Per `07_UI_UX_SPEC.md` §4–6. Dashboard computations go in a small pure helper (`ui/metrics.py` or inside the page) using pandas over `store.all_runs()`.

### Phase 6: Polish
CSS classes, pills, consistent icons, microcopy table, empty states.

### Phase 7: Deploy
- `.gitignore`: `.venv/`, `__pycache__/`, `data/runs.db`, `.DS_Store`
- **Commit `samples/` and `data/vendor_master.csv`** (the cloud app needs them).
- Push → share.streamlit.io → deploy `app.py` → run all 6 scenarios on the live URL.

### Phase 8: Demo prep
Follow `10_DEMO_SCRIPT.md`. Reset data before recording.

---

## Day-7 submission email
To: hiring coordinator · Subject: `ASA Case Study — Arun Kaarthikeyan — PS-2`
Body: 2 lines + **Live app:** <streamlit url> · **Demo video:** <loom url> · **Repo:** <github url> · "Assumptions and design decisions are in docs/08 in the repo."
