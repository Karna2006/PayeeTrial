# 02 · Tech Stack & Constraints

## Hard constraints

1. **₹0 total cost.** Only open-source libraries and free hosting. No paid APIs, no API keys required to run.
2. **Runs fully offline** on the presenter's laptop. The live interview demo must not depend on Wi-Fi or any third-party uptime.
3. **Python only.** One language, one process, no separate frontend build step.
4. **Deployable in under 10 minutes** to Streamlit Community Cloud from a public GitHub repo (the "live, runnable link" deliverable).
5. **Deterministic.** The same input gives the same decision, every run. No randomness in decisions.
6. **No Zamp / Pace tools** (explicitly banned in the brief).

---

## The stack

| Layer | Choice | Version | Why this, not something else |
|---|---|---|---|
| Language | **Python** | 3.10+ | Fastest to build; everything below is Python |
| UI + server | **Streamlit** | ≥ 1.40 | Built-in `st.status` gives the live stage-by-stage run view for free; forms, charts and tables out of the box; one-command deploy. *Rejected:* Next.js (two codebases, slower), Flask + HTML (hand-built UI), n8n (fair-code licence, harder to show custom logic) |
| Data handling | **pandas** | ≥ 2.0 | Vendor master lookups and dashboard aggregation |
| Database | **SQLite** (stdlib `sqlite3`) | built-in | Zero setup, a single file, survives restarts, perfect for an audit log. *Rejected:* Supabase / Firebase (accounts, network dependency) |
| PDF text extraction | **pypdf** | ≥ 4.0 | Pure Python, no system dependencies, reads digital PDFs |
| Fuzzy name matching | **rapidfuzz** | ≥ 3.0 | Fast, MIT licensed; `token_sort_ratio` handles word-order differences. Falls back to stdlib `difflib` if missing |
| ID validation (cross-check) | **python-stdnum** | ≥ 1.20 | Independent GSTIN / PAN validator used in tests to prove our checksum is correct |
| Test-document generation | **reportlab** | ≥ 4.0 | Generates realistic synthetic GST certificate, PAN card and cheque PDFs |
| Charts | **Streamlit native charts** (`st.bar_chart`) | built-in | No extra dependency; enough for status split and top failures |
| Optional LLM | **Ollama** running **qwen2.5:7b-instruct** (or `llama3.1:8b`) | local | Open-source, local, free. Used ONLY to polish the vendor email's tone. Off by default; auto-detected; falls back to the template |
| Tests | **pytest** | ≥ 8 | Scenario regression tests |
| Version control | **git** + GitHub (public repo) | | Needed for the Streamlit Cloud deploy |
| Hosting | **Streamlit Community Cloud** (free) | | Live link for the submission email |

### `requirements.txt` (exact)
```
streamlit>=1.40
pandas>=2.0
pypdf>=4.0
rapidfuzz>=3.0
python-stdnum>=1.20
reportlab>=4.0
pytest>=8.0
```
Ollama is NOT in requirements. It's an optional local install (`ollama pull qwen2.5:7b-instruct`).

---

## Third-party APIs

**None required.** Everything is local.

| Would be used in production | Free / open alternative used in v1 |
|---|---|
| GSTN public search API (verify GSTIN is active) | GSTIN checksum + status read from the uploaded certificate |
| NSDL / Protean PAN verification | PAN format + holder type + match against PAN card PDF and GSTIN |
| Penny-drop bank verification (paid) | Account holder name on the form + cancelled cheque cross-check |
| Email sending (SMTP / Resend) | Outbox table in SQLite, shown in the UI |
| Full IFSC branch DB | 18-bank IFSC-prefix map in code (swap-in: Razorpay IFSC dataset, MIT) |

---

## Where the LLM is and isn't used (be ready to defend this)

| Task | Rules or LLM? | Reason |
|---|---|---|
| GSTIN checksum, PAN format, IFSC format | Rules | Mathematically defined; an LLM can only be worse |
| PAN ↔ GSTIN, state code ↔ address | Rules | Exact string logic |
| Name matching (bank holder vs legal name) | Rules (fuzzy + normalisation) | Needs a tunable threshold and an explainable score |
| Document classification | Rules (keyword fingerprints on extracted text) | Standard government formats; predictable |
| Decision (approve / pending / reject) | Rules | Must be auditable and identical every time |
| Vendor email wording | **Template; LLM optional polish** | Tone is a language task. Guardrail: every ID in the asks must survive the rewrite, or we keep the template |
| *v2:* extraction from scanned or odd-format docs | LLM / vision | Where rules genuinely break down |

---

## Environment variables (all optional)

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Model used for email polish |

---

## Deployment

**Local (for the interview):**
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/make_samples.py      # generates samples/ + data/vendor_master.csv
streamlit run app.py                # opens http://localhost:8501
```

**Streamlit Community Cloud (for the "live link"):**
1. Push the repo to GitHub (public). Commit `samples/` and `data/vendor_master.csv`; do NOT commit `data/runs.db`.
2. share.streamlit.io → New app → pick repo → main file `app.py` → Deploy.
3. Note: the cloud filesystem is ephemeral, so the dashboard resets when the app sleeps. That's fine; say so if asked. Ollama is not available there; the template email is used automatically.

---

## Performance budget

- Full pipeline: < 500 ms of compute for 3 PDFs.
- "Demo pacing" toggle adds 0.6 s per stage so humans can watch it run. Default ON in the UI, OFF in tests.
