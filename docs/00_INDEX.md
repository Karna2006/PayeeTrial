# 00 · Planning Pack Index

Read in this order. Total ≈ 25 min.

| # | Doc | Purpose | Read time |
|---|---|---|---|
| 01 | `01_PRD.md` | What and why: one-liner, users, 5 MVP features, non-goals, success criteria, glossary | 4 min |
| 02 | `02_TECH_STACK.md` | Exact stack, constraints, rules-vs-LLM split, deploy | 3 min |
| 03 | `03_DATA_SCHEMA.md` | Every model and field, DB table, reference data, folder layout | 4 min |
| 04 | `04_USER_FLOWS.md` | Flows A–E step by step, settings, error states | 3 min |
| 05 | `05_RULES_SPEC.md` | The brain: 27 checks, severities, messages, decision logic, algorithms | 6 min |
| 06 | `06_TEST_SCENARIOS.md` | 6 scenarios with exact values and expected outcomes | 3 min |
| 07 | `07_UI_UX_SPEC.md` | Visual rules + wireframes for every page | 4 min |
| 08 | `08_ASSUMPTIONS_AND_DECISIONS.md` | Assumptions, decisions, limits, roadmap (your interview cheat sheet) | 3 min |
| 09 | `09_PLAN.md` | Phased one-day build with exit checks | 2 min |
| 10 | `10_DEMO_SCRIPT.md` | Video script, live run order, likely questions + answers | 4 min |
| 11 | `11_PRODUCTION_READINESS.md` | Security boundary, API adapter design, scale path, and launch gates | 6 min |
| 12 | `12_REFERENCE_REPO_REVIEW.md` | External sample data and reuse decisions | 3 min |
| 13 | `13_TESTING_PIPELINE.md` | Local test command, safe fixtures, automated layers, edge cases, CI, manual demo smoke test | 5 min |

**How to use with an AI coding agent (Claude Code or Codex):**
1. `CLAUDE.md` (Claude Code) and `AGENTS.md` (Codex) in the repo root are read automatically.
2. First prompt: *"Read CLAUDE.md and docs/00_INDEX.md through docs/09_PLAN.md. Ask me up to 5 clarifying questions only if something blocks Phase 0–2; otherwise propose your Phase 0 plan."*
3. Go phase by phase per `09_PLAN.md`. Commit after each phase.
