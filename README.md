# 🛡️ VendorGuard: vendor onboarding, verified

> Zamp · AI Solutions Analyst case study · **PS-2: Vendor onboarding, from submission to approval**

VendorGuard takes a vendor's onboarding submission (form + PDFs), cross-checks every field and document against each other and against the existing vendor master, and returns **Approved / Pending / Rejected**, with the reasoning visible stage by stage and a ready-to-send message telling the vendor exactly what to fix.

- **26 checks across 5 stages:** intake → identity (PAN + GSTIN) → bank → document cross-check → duplicate & fraud screening
- **Catches what field validators miss:** the PAN inside the GSTIN, GSTIN state vs address, documents classified by content, third-party bank accounts, bank accounts shared with existing vendors, unrequested bank changes on resubmission
- **Rules decide, AI assists:** deterministic, auditable decisions; an optional local LLM only polishes email tone
- **₹0, open-source, fully offline**

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/make_samples.py
streamlit run app.py
```

Then on **Submit & Verify**, load a demo scenario and click **▶ Run verification**.

## Demo scenarios

| # | Scenario | Expected |
|---|---|---|
| 1 | Happy path | APPROVED |
| 2 | Cross-field inconsistencies (PAN typo + GSTIN from the wrong state) | PENDING · Awaiting vendor |
| 3 | Third-party bank account already used by another vendor | REJECTED |
| 4 | Wrong documents (sister company's GST cert; "cheque" that's a PAN card) | PENDING · Awaiting vendor |
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
| [`docs/05_RULES_SPEC.md`](docs/05_RULES_SPEC.md) | **All 26 checks**: logic, severity, vendor and internal messages, decision logic, algorithms |
| [`docs/06_TEST_SCENARIOS.md`](docs/06_TEST_SCENARIOS.md) | 6 scenarios with exact data and expected outcomes; test assertions |
| [`docs/07_UI_UX_SPEC.md`](docs/07_UI_UX_SPEC.md) | Design vibe, colour tokens, wireframes for every page, components, microcopy |
| [`docs/08_ASSUMPTIONS_AND_DECISIONS.md`](docs/08_ASSUMPTIONS_AND_DECISIONS.md) | Assumptions, design decisions, known limits, v2 roadmap |
| [`docs/09_PLAN.md`](docs/09_PLAN.md) | One-day phased build plan with exit checks |
| [`docs/10_DEMO_SCRIPT.md`](docs/10_DEMO_SCRIPT.md) | 5-min video script, live run order, interview Q&A |
| [`CLAUDE.md`](CLAUDE.md) / [`AGENTS.md`](AGENTS.md) | Rulebook for Claude Code / Codex |

All test data is synthetic.
