# 02 · Tech Stack & Constraints

## Hard constraints

1. **Offline core.** The application runs without an API key. OpenRouter's selected `:free` endpoint is opt-in and rate-limited; use synthetic documents for the demo.
2. **Local demo path remains available.** AI review needs internet only when enabled; document checks and rules continue to run locally when it is off.
3. **Python only.** One language, one process, no separate frontend build step.
4. **Deployable in under 10 minutes** to Streamlit Community Cloud from a public GitHub repo (the "live, runnable link" deliverable).
5. **Deterministic rules.** The same submission and local PDF text give the same rules outcome. Optional AI can only add a human-review hold; it cannot produce an approval.
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
| Document AI and email polish | **NVIDIA Nemotron 3.5 Super VL** through OpenRouter (`nvidia/nemotron-3.5-super-vl:free`) | optional HTTPS API | One model handles PDF classification, evidence extraction, advisory quality score, and optional email rewrite. Free endpoint is rate-limited and not suitable for real PII; off unless enabled and a key is configured |
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

---

## Third-party APIs

No external API is required for the core workflow. OpenRouter review and email polishing are optional external calls using one model.

| Would be used in production | Free / open alternative used in v1 |
|---|---|
| GSTN public search API (verify GSTIN is active) | GSTIN checksum + status read from the uploaded certificate |
| NSDL / Protean PAN verification | PAN format + holder type + match against PAN card PDF and GSTIN |
| Penny-drop bank verification (paid) | Account holder name on the form + cancelled cheque cross-check |
| OpenRouter PDF review (optional) | Local keyword classification and text-layer extraction |
| Email sending | Outbox table in SQLite, shown in the UI |
| Full IFSC branch DB | 18-bank IFSC-prefix map in code (swap-in: Razorpay IFSC dataset, MIT) |

---

## Where the LLM is and isn't used (be ready to defend this)

| Task | Rules or LLM? | Reason |
|---|---|---|
| GSTIN checksum, PAN format, IFSC format | Rules | Mathematically defined; an LLM can only be worse |
| PAN ↔ GSTIN, state code ↔ address | Rules | Exact string logic |
| Name matching (bank holder vs legal name) | Rules (fuzzy + normalisation) | Needs a tunable threshold and an explainable score |
| Document classification | Rules by default; OpenRouter optional | AI reads visual layouts and scans; local classifier remains the offline fallback |
| Document field extraction | Local rules supply check inputs; AI shows candidate fields and page evidence | AI candidate fields never feed verification checks; scans and classification conflicts require human review |
| Document quality score | AI proposes classification/readability; code caps completeness (classification 0–30, completeness 0–40, readability 0–30) to fields with supporting quotes | Advisory evidence-quality score, not authenticity or vendor risk |
| Decision (approve / pending / reject) | Rules | Must be auditable and identical every time |
| Vendor email wording | **Template; optional OpenRouter suggestion from the same model** | The rewrite is displayed as an unapproved draft only; it never replaces the deterministic message of record |
| Final approval/rejection | Rules | The model has no decision authority; disagreements and visual-only extraction become review items |

---

## Environment variables (all optional)

| Var | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | unset | Enables optional document review and email polish; keep in environment or Streamlit secrets, never Git |
| `OPENROUTER_MODEL` | `nvidia/nemotron-3.5-super-vl:free` | Shared model ID for both AI features |

The free endpoint is explicitly not for confidential information or personal data; synthetic assignment examples only. Free usage currently has a 50-request/day cap (20 requests/minute), subject to change. See [OpenRouter model details](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free) and its rate limits before use.

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
3. Note: the cloud filesystem is ephemeral, so the dashboard resets when the app sleeps. The template email remains available if OpenRouter is unavailable.

---

## Performance budget

- Full pipeline: < 500 ms of compute for 3 PDFs.
- "Demo pacing" toggle adds 0.6 s per stage so humans can watch it run. Default ON in the UI, OFF in tests.
