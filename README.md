# 🛡️ PayeeTrail: Trust the payee. Trace every change.

> Zamp · AI Solutions Analyst case study · **PS-2: Vendor onboarding, from submission to approval**

PayeeTrail takes a vendor's onboarding submission (form + PDFs), cross-checks every field and document against each other and against the existing vendor master, and returns **Approved / Pending / Rejected**, with the reasoning visible stage by stage and a ready-to-send message telling the vendor exactly what to fix.

- **27 core checks across 5 stages** plus conditional document classification, conflict, AI review, duplicate-file, and analyst-review findings: intake -> identity (PAN + GSTIN) -> bank -> document cross-check -> duplicate & fraud screening
- **Catches what field validators miss:** the PAN inside the GSTIN, GSTIN state vs address, documents classified by content, third-party bank accounts, bank accounts shared with existing vendors, unrequested bank changes on resubmission
- **Rules decide, AI assists:** one OpenRouter model can classify PDFs, extract page evidence, score document quality, and suggest email wording; deterministic checks still own the final outcome
- **Offline by default:** AI is opt-in. The same model handles document review and optional email polishing
- **Bounded PDF intake:** size, page-count, and extracted-text limits; scanned or conflicting AI extractions go to human review
- **Audited document review:** reviewers can confirm or correct uncertain OCR candidates against the original PDF; original AI values and each review event remain in the audit trail without creating a new vendor submission version
- **One-click document autofill:** selectable PDF text fills blank matching form fields locally; optional AI OCR suggests evidence-cited values for scans, while existing form values are never overwritten
- **Duplicate and near-duplicate screening:** exact PDF SHA-256 matches are flagged even after renaming; similar legal names in the vendor master route to human review only

The current build remains an assignment prototype, not a production vendor portal. OpenRouter's free NVIDIA Nemotron 3.5 Super VL endpoint provides optional OCR-like extraction for scanned pages; extracted values remain unconfirmed until a reviewer checks the original. The free endpoint may log prompts and use them to improve the provider's products: use only synthetic demo data for any AI feature; never send real vendor documents or contact or financial identifiers. Its scale path—including privacy-approved model hosting, persistent storage, access control, and async processing—is documented in [`docs/11_PRODUCTION_READINESS.md`](docs/11_PRODUCTION_READINESS.md).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/make_samples.py
streamlit run app.py
```

Then on **Submit & Verify**, load a demo scenario and click **▶ Run verification**.

### Optional AI document review and email polishing

Both features use the same OpenRouter model, `nvidia/nemotron-3.5-super-vl:free`. Create a free OpenRouter API key and add `OPENROUTER_API_KEY = "..."` to `.streamlit/secrets.toml` (or set the environment variable), then enable either option in Settings. Document review sends selected PDFs to OpenRouter. Email polishing sends the generated email body, which can contain vendor or contact names, references, and correction requests. The free endpoint is rate-limited and may log prompts or use them to improve provider products. Use synthetic demo data only; never put a key in a commit or chat.


## Test the project

The test suite uses synthetic data and mocked provider responses, so it needs no API keys or real vendor documents:

```bash
python scripts/make_samples.py
python scripts/make_scan_sample.py
python -m pytest -q
```

GitHub Actions runs the same suite on pushes and pull requests. See [`docs/13_TESTING_PIPELINE.md`](docs/13_TESTING_PIPELINE.md) for the test layers, edge-case coverage, local temp-directory workaround, and manual demo checks.

## Demo scenarios

| # | Scenario | Expected |
|---|---|---|
| 1 | Happy path | APPROVED |
| 2 | Cross-field inconsistencies (PAN typo + GSTIN from the wrong state) | PENDING · Awaiting vendor |
| 3 | Third-party bank account already used by another vendor | REJECTED |
| 4 | Wrong documents (sister-company GST cert; two distinct PAN cards, one uploaded as a cheque) | PENDING - Awaiting vendor |
| 5 | Resubmission of #2 that quietly swaps the bank account (**run after #2**) | PENDING · Compliance review |
| 6 | Proprietorship paid into the owner's personal account (legitimate) | APPROVED |

## Planning docs

| Doc | What's inside |
|---|---|
| [`docs/00_INDEX.md`](docs/00_INDEX.md) | Reading order |
| [`docs/01_PRD.md`](docs/01_PRD.md) | Problem, users, MVP features, **non-goals**, success criteria, glossary |
| [`docs/02_TECH_STACK.md`](docs/02_TECH_STACK.md) | Stack, constraints, where the LLM is and isn't used, deployment |
| [`docs/03_DATA_SCHEMA.md`](docs/03_DATA_SCHEMA.md) | Every data model, DB table, reference data, folder layout |
| [`docs/04_USER_FLOWS.md`](docs/04_USER_FLOWS.md) | Step-by-step flows incl. resubmission, error states |
| [`docs/05_RULES_SPEC.md`](docs/05_RULES_SPEC.md) | Core checks and conditional AI review gate: logic, severity, messages and decision rules |
| [`docs/06_TEST_SCENARIOS.md`](docs/06_TEST_SCENARIOS.md) | 6 scenarios with exact data and expected outcomes; test assertions |
| [`docs/07_UI_UX_SPEC.md`](docs/07_UI_UX_SPEC.md) | Design vibe, colour tokens, wireframes for every page, components, microcopy |
| [`docs/08_ASSUMPTIONS_AND_DECISIONS.md`](docs/08_ASSUMPTIONS_AND_DECISIONS.md) | Assumptions, design decisions, known limits, v2 roadmap |
| [`docs/09_PLAN.md`](docs/09_PLAN.md) | One-day phased build plan with exit checks |
| [`docs/10_DEMO_SCRIPT.md`](docs/10_DEMO_SCRIPT.md) | 5-min video script, live run order, interview Q&A |
| [`docs/11_PRODUCTION_READINESS.md`](docs/11_PRODUCTION_READINESS.md) | Security and scaling architecture, API integrations, production gates |
| [`docs/12_REFERENCE_REPO_REVIEW.md`](docs/12_REFERENCE_REPO_REVIEW.md) | Reference repo data and reuse decisions |
| [`docs/13_TESTING_PIPELINE.md`](docs/13_TESTING_PIPELINE.md) | Local and CI test commands, safe fixtures, edge-case coverage, manual checks |
| [`CLAUDE.md`](CLAUDE.md) / [`AGENTS.md`](AGENTS.md) | Rulebook for Claude Code / Codex |

All test data is synthetic.
