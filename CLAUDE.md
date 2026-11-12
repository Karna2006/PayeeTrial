# CLAUDE.md: Rulebook for AI coding agents on PayeeTrail

You are helping build **PayeeTrail**, a vendor-onboarding verification app for a one-day take-home case study (Zamp, AI Solutions Analyst, PS-2). Read this file fully before any task.

## 1. Read these first (source of truth)

| File | Read when |
|---|---|
| `docs/01_PRD.md` | Always: what we build and **what we don't** (Non-goals §5) |
| `docs/05_RULES_SPEC.md` | Any change to `engine/`: every check, severity and message is defined there |
| `docs/03_DATA_SCHEMA.md` | Any change touching data shapes or the DB |
| `docs/07_UI_UX_SPEC.md` | Any change to `app.py` or `ui/` |
| `docs/06_TEST_SCENARIOS.md` | Before claiming anything works |
| `docs/09_PLAN.md` | To know which phase we're in |

**If code and docs disagree, the docs win.** If you believe the docs are wrong, say so and propose the doc change; don't silently diverge.

## 2. Current state

- `engine/` and `scripts/make_samples.py` are a **working, tested reference implementation**. All 6 scenarios produce the expected decision. **Don't rewrite them.** Extend them only where `09_PLAN.md` says so (e.g. `REQUESTED_BY` + `classify_changes`).
- Not yet built: `app.py`, `ui/`, `tests/`, `.streamlit/config.toml` styling details.

## 3. Hard constraints (never violate)

1. **₹0 / open-source only.** No paid APIs, no API keys, no cloud services besides Streamlit Community Cloud hosting.
2. **Must run fully offline.** No network calls in the pipeline. (The only optional network call is to local Ollama at `localhost`.)
3. **Deterministic decisions.** No LLM in any check or in `decide()`. The LLM is allowed only in `messages.polish_with_llm`, behind its guardrail.
4. **Stack is fixed:** Python 3.10+, Streamlit, pandas, SQLite (stdlib), pypdf, rapidfuzz, python-stdnum, reportlab, pytest. Ask before adding any dependency.
5. **Respect Non-goals** (`01_PRD.md` §5): no auth, no real email sending, no OCR, no external verification APIs, no dark mode, no Docker, no React/Next.js.
6. **Never leak internal fraud context into vendor-facing text** (e.g. another vendor's ID or name). Vendor email ≠ internal note.

## 4. Coding standards

- **Small, modular files.** No file over ~300 lines. One page = one file in `ui/`.
- `engine/` must **never import streamlit**. It's pure logic, testable with pytest.
- `ui/` never re-implements rules; it only calls `engine/`.
- Type hints on public functions; short docstrings that say *why*, not *what*.
- Check IDs, severities, thresholds and messages are constants matching `05_RULES_SPEC.md` exactly.
- No silent `except: pass` in the engine. UI may catch and show a friendly `st.error`.
- Use `st.session_state` keys with prefixes: `f_` form fields, `ui_` UI state, `last_run` for the current result.
- Paths via `pathlib.Path(__file__).resolve().parent…`, never relative to the CWD.
- Keep `app.py` ≤ 60 lines (config, CSS, sidebar, routing).

## 5. Workflow rules

1. **At the start of each phase** (see `09_PLAN.md`): state your plan in ≤ 10 bullet lines (files to touch, what changes, how you'll verify) and **wait for approval**. Once approved, carry out the whole phase without asking per file.
2. Make small, reviewable changes. After each phase: run the verification commands below, show the output, and propose a commit message.
3. **Never claim it works without running it.** For UI work, at minimum run `python -c "import app"` style import checks plus the pytest suite; describe what to click to verify manually.
4. If something in the spec is ambiguous, pick the simplest option consistent with the PRD, note the assumption in `docs/08_ASSUMPTIONS_AND_DECISIONS.md`, and tell me.
5. Don't refactor working code that isn't part of the current phase.
6. If a phase is running long, propose a cut (see "Buffer" in `09_PLAN.md`) rather than rushing.

## 6. Commands

```bash
# setup
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# generate demo data (scenarios JSON + 17 PDFs + vendor master)
python scripts/make_samples.py

# run the app (http://localhost:8501)
streamlit run app.py

# tests
pytest -q

# quick engine smoke test (all scenarios, no UI)
python -m pytest tests/test_scenarios.py -q

# reset the audit DB
rm -f data/runs.db

# optional local LLM for email polish
ollama pull qwen2.5:7b-instruct && ollama serve
```

## 7. Definition of done (whole project)

- `pytest -q` green.
- In the UI, the 6 scenarios give: #1 APPROVED · #2 PENDING/Awaiting vendor · #3 REJECTED · #4 PENDING/Awaiting vendor · #5 (after #2) PENDING/Compliance review · #6 APPROVED.
- Live run view, decision card, 4 tabs, dashboard, run detail and outbox all work with no Streamlit errors.
- Deployed on Streamlit Community Cloud and the live URL passes the same 6 scenarios.

## 8. Folder map

```
app.py                 entry: config + sidebar + routing
ui/components.py       pills, risk bar, check rows, decision card, diff table, CSS
ui/page_submit.py      scenario loader + form + live run + decision + tabs
ui/page_dashboard.py   KPIs, charts, work queue, history
ui/page_run_detail.py  full record of one run + version history
ui/page_outbox.py      generated vendor emails
engine/validators.py   PAN/GSTIN/IFSC/name helpers + reference data
engine/documents.py    PDF → ParsedDoc (classify by content)
engine/pipeline.py     5 stages, 26 checks, decide()
engine/messages.py     vendor email, internal note, optional Ollama polish
engine/store.py        SQLite append-only audit log
scripts/make_samples.py  demo data generator
samples/               6 scenario JSONs + docs/*.pdf
data/vendor_master.csv existing vendors
tests/                 pytest
docs/                  planning pack (read-only unless updating specs)
```
