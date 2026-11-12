# 07 · UI / UX Specification

The UI is graded ("we expect an intuitive, well-designed interface with a **live run view** and a **dashboard**"). The interviewer will watch it live. Optimise for: *a non-technical buyer understands what happened in 10 seconds.*

---

## 1. Design vibe

**"Calm control room."** Minimal, light, high-contrast, inspired by **Linear** and **Stripe Dashboard**: lots of white space, one accent colour, colour used **only** to mean something (status). No gradients, no emojis as decoration (emojis allowed only as status icons ✅ ⚠️ ❌ ℹ️), no stock illustrations.

### Colour tokens

| Token | Hex | Use |
|---|---|---|
| `accent` | `#4F46E5` (indigo-600) | primary buttons, links, active nav |
| `text` | `#111827` | body |
| `muted` | `#6B7280` | secondary text, captions |
| `bg` | `#FFFFFF` | page |
| `surface` | `#F6F7F9` | cards, sidebar |
| `border` | `#E5E7EB` | card borders, dividers |
| `approved` | `#059669` text on `#ECFDF5` bg | APPROVED pill, pass |
| `pending` | `#B45309` text on `#FFFBEB` bg | PENDING pill, warn |
| `rejected` | `#B91C1C` text on `#FEF2F2` bg | REJECTED pill, fail |
| `info` | `#1D4ED8` text on `#EFF6FF` bg | info rows, resubmission banner |

### Typography
- Streamlit default sans (Source Sans) is fine; set `font = "sans serif"` in theme.
- Page title 28px semibold; section headers 18px semibold; body 15px; captions 13px muted.
- Monospace (`st.code` / backticks) for IDs: PAN, GSTIN, IFSC, account numbers, refs.

### `.streamlit/config.toml`
```toml
[theme]
base = "light"
primaryColor = "#4F46E5"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F6F7F9"
textColor = "#111827"
font = "sans serif"

[server]
headless = true
```

### Shape rules
- Cards: 1px `border`, 12px radius, 16–20px padding (inject minimal CSS via `st.markdown(unsafe_allow_html=True)` **once** in `components.py`).
- Status pills: fully rounded, 12px uppercase semibold, letter-spacing 0.04em.
- Max 2 levels of nesting. Never put a card inside a card inside an expander.

---

## 2. Layout & navigation

- `st.set_page_config(page_title="PayeeTrail", page_icon="🛡️", layout="wide")`
- **Left sidebar** (fixed):
  - Logo line: **🛡️ PayeeTrail** + caption "Trust the payee. Trace every change."
  - Nav (`st.radio`, label hidden): **Submit & Verify** · **Dashboard** · **Run detail** · **Outbox**
  - Divider
  - **Settings** expander: Demo pacing (toggle, ON) · Polish email with local LLM (toggle, OFF, disabled if Ollama not detected; status caption) · Reset demo data (confirm checkbox + button)
  - Footer caption: "Rules engine v1 · 26 checks · 100% offline"
- **Main area:** max readable width; use `st.columns` for side-by-side.
- Navigation between pages via `st.session_state["page"]` (so buttons like "Open run" can switch pages).

---

## 3. Page: Submit & Verify (the demo page)

```
┌────────────────────────────────────────────────────────────────────────┐
│ Submit & Verify                                                        │
│ Run a vendor submission through 26 checks across 5 stages.             │
│                                                                        │
│ [ Load demo scenario ▼  01 · Happy path: clean submission ] [ Load ]   │
│   caption: expected outcome: APPROVED  (shown after selecting)         │
│                                                                        │
│ ↻ Resubmission detected: will be v2 of VS-2026-102 (v1: PENDING ·    │  ← info banner, only if ref exists
│   Awaiting vendor)                                                     │
│                                                                        │
│ ▸ Company  ▸ Address  ▸ Contact  ▸ Bank  ▸ Documents   (form, 2-col)   │
│                                                                        │
│                                   [ ▶ Run verification ] (primary)     │
├────────────────────────────────────────────────────────────────────────┤
│ LIVE RUN                                                               │
│ Documents read: [GST cert ✓ nimbus_gst…] [PAN card ✓] [Cheque ✓]       │
│ ✅ 1 · Intake & completeness           4 passed            12 ms       │
│ ✅ 2 · Identity: PAN + GSTIN           5 passed             3 ms       │
│ ❌ 3 · Bank details                    1 failed · 1 warn    2 ms  ▾    │
│      ✅ IFSC format: SBIN0001789 is well-formed (State Bank of India)  │
│      ⚠️ IFSC matches stated bank: IFSC prefix SBIN = SBI, form says…   │
│      ❌ Account holder = legal entity: held by 'Kaveri Traders'…       │
│ …                                                                      │
├────────────────────────────────────────────────────────────────────────┤
│ DECISION                                                               │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ [REJECTED]  Closed: rejected            Risk ███████████ 100 High │   │
│ │ Account held by 'Kaveri Traders', an unrelated party to…         │   │
│ │ 🚩 Fraud signals: ACCOUNT_NAME · DUP_BANK                        │   │
│ │ 18 passed · 2 failed · 2 warnings · 9 ms · run #7 · v1           │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│ [📧 Vendor email] [📝 Internal note] [🔀 Changes vs previous] [🧾 Raw] │
└────────────────────────────────────────────────────────────────────────┘
```

### Form spec (`st.form("submission")`)
| Section | Fields (widget) |
|---|---|
| Company | Legal name (text) · Trade name (text) · Entity type (selectbox of 5) · Proprietor's full name (text, **only shown if Proprietorship**; because widgets inside st.form don't rerun, put entity_type *outside* the form or show the field always with help text "Only for proprietorships") · PAN (text) · GSTIN (text) |
| Address | Line 1 · City · State (selectbox of 36 states, sorted) · PIN code |
| Contact | Name · Email · Phone · Website (optional) |
| Bank | Account holder name · Account number · IFSC · Bank name |
| Documents | `st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)` + "Attached from demo scenario" list (chips) with a "Clear attached" button outside the form |
| Hidden | `submission_ref`: from the loaded scenario, or a new `VS-2026-{next}` for a manual entry. Show it as a read-only caption: "Reference: VS-2026-102" |

Field keys in `st.session_state` use dot paths, e.g. `f_address.state`, so "Load scenario" can set them, then `st.rerun()`.

### Live run spec
- Use `st.status(label, expanded=False/True)` per stage, iterating the pipeline generator.
- While running: label "⏳ {n} · {stage}…". After: label "{icon} {n} · {stage}: {summary}", `state="complete"` or `"error"` for failures.
- **Expand automatically** stages that have a fail or warn; collapse all-pass stages.
- Row format: `{icon} **{name}**: {detail}`; for failures add a muted caption line: "→ asks vendor: {vendor_ask}" (truncate at 160 chars) or "→ internal: {internal_note}".
- Above the stages, the document chips row: `filename → detected type` (red chip if `unknown` or if the type disagrees with an obvious filename hint like "cheque" → mismatch chip "named like a cheque, reads as PAN card").

### Decision card spec
- Left: status pill (colour by status) + queue text.
- Right: risk bar (`st.progress(score/100)`) + "{score} · {level}".
- Headline in 18px.
- Fraud signal row (only if any): 🚩 + check_ids as small red tags.
- Footer: counts · duration · run id · version.

### Tabs under the card
1. **📧 Vendor email**: "To: …", "Subject: …" (bold), body in a bordered box (`st.text_area` disabled or `st.code(language=None)` for copy); caption "Generated by: template / ollama:qwen2.5".
2. **📝 Internal note**: `st.code` block; caption "Visible to procurement/compliance only."
3. **🔀 Changes vs previous**: only if version > 1. Table: Field · Previous · Now · Requested? (✅ requested / ⚠️ unrequested), per the mapping in Rules Spec §5.
4. **🧾 Raw record**: `st.json` of `{submission, documents, results, decision}`.

---

## 4. Page: Dashboard

```
┌───────────────────────────────────────────────────────────────────────┐
│ Dashboard                                         [ ↻ Refresh ]        │
│ ┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐          │
│ │Runs  8 ││Approved││Pending ││Rejected││Avg risk││Avg time│          │
│ │        ││ 2 (25%)││   4    ││   2    ││   38   ││ 11 ms  │          │
│ └────────┘└────────┘└────────┘└────────┘└────────┘└────────┘          │
│ ┌ Status split (bar) ──────────┐┌ Top failing checks (horiz bar) ──┐  │
│ └──────────────────────────────┘└──────────────────────────────────┘  │
│ WORK QUEUE (latest version per ref, PENDING only)                     │
│  Compliance review (1) · Awaiting vendor (2) · Procurement review (0) │
│  ref · vendor · version · risk · headline · [Open] [Resubmit]         │
│ RUN HISTORY  [status filter ▼] [search…]                              │
│  # · time · ref · v · vendor · status · queue · risk · headline       │
│  [ Open run ▼ ] [Open]                                                │
└───────────────────────────────────────────────────────────────────────┘
```

- KPIs with `st.metric`. "Approved" shows the count plus % in the delta slot (neutral colour).
- Status split: `st.bar_chart` with colours by status (pass `color` per series). Fall back to a simple table if colouring is fiddly.
- Top failing checks: count failed results by `check_id` across **all runs**, top 8, horizontal bar.
- Work queue: group by queue with subheaders; each row has **Open** (→ Run detail) and **Resubmit** (→ Submit page prefilled with that version's submission, attached docs cleared, banner shown).
- History: `st.dataframe` with column config: status as coloured text, risk as `ProgressColumn` (0–100).
- **Empty state:** "No runs yet. Go to Submit & Verify and load a demo scenario." + button.

---

## 5. Page: Run detail

- Selector at top: "Run #…" (selectbox of all runs, label "#{id} · {ref} v{version} · {vendor} · {status}"), defaulting to `session_state.selected_run`.
- Decision card (same component).
- **Version history for this ref**: small table of all versions (v, time, status, queue, risk), each with an Open button.
- Columns: left = checks grouped by stage (static, same row component as the live view, all expanded for failed stages); right = Documents (each: filename, detected type, extracted fields as key/value), Submission (key/value table).
- Tabs: Vendor email · Internal note · Changes vs previous · Raw JSON.

---

## 6. Page: Outbox

- A list of all generated vendor emails, newest first: status pill · **Subject** · To · ref/version · time.
- Each in an expander: full body (`st.code(language=None)` so it has a copy button) + caption "Not sent. v1 has no SMTP by design; in production this queue feeds the mail service."
- Filter by status.

---

## 7. Reusable components (`ui/components.py`)

| Function | Renders |
|---|---|
| `inject_css()` | One-time CSS: card, pill, tag, chip classes |
| `status_pill(status) -> str` | HTML span with colour by status |
| `risk_bar(score, level)` | progress + caption |
| `check_row(result: dict)` | icon + bold name + detail (+ ask/note caption) |
| `stage_summary(results) -> (icon, text, state)` | "3 passed · 1 failed" etc. |
| `decision_card(decision, meta)` | the card |
| `email_view(email)` | To / Subject / body |
| `diff_table(prev_sub, sub, prev_results)` | the requested/unrequested table |
| `doc_chips(parsed_docs)` | filename → type chips |

---

## 8. Microcopy (use exactly)

| Where | Text |
|---|---|
| Submit page subtitle | "Run a vendor submission through 26 checks across 5 stages." |
| Run button | "▶ Run verification" |
| Running toast | "Verifying {legal_name}…" |
| Saved toast | "Saved as run #{id} (v{version})" |
| Resubmission banner | "↻ Resubmission detected: this will be v{n} of {ref} (v{n-1} was {status} · {queue})." |
| Approved headline | "All identity, bank, document and fraud checks passed" |
| Internal-note caption | "Visible to procurement/compliance only. Never sent to the vendor." |
| Outbox caption | "Not sent. v1 has no SMTP by design; in production this queue feeds the mail service." |
| Empty dashboard | "No runs yet. Go to Submit & Verify and load a demo scenario." |

---

## 9. Accessibility & polish checklist
- [ ] Status is never conveyed by colour alone (always the icon or word too).
- [ ] All IDs are monospace.
- [ ] No horizontal scroll at 1280px width (the demo screen).
- [ ] Browser zoom 110% still looks right (screen-share readability).
- [ ] No Streamlit warnings or exceptions visible anywhere during the 6 scenarios.
- [ ] Page loads in < 2 s.
