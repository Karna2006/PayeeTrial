# 04 · User Flows

Four flows cover everything. Each step names the screen, what the user does, and what the system does.

---

## Flow A: First-time submission (happy path)

1. **Analyst opens the app** → lands on **Submit & Verify** (default page in the sidebar).
2. At the top: the **"Load demo scenario"** dropdown. Picks *"01 · Happy path"* → clicks **Load**.
   - The system fills every form field from `samples/01_happy_path.json` and lists the 3 sample PDFs under "Attached documents" (with the option to remove or add uploads).
   - (Real usage: types into the form and drags in PDFs instead. Both paths must work.)
3. Reviews the form, which has 5 sections: **Company · Address · Contact · Bank · Documents**.
   - Selecting entity type *Proprietorship* reveals the "Proprietor's full name" field.
4. Clicks **▶ Run verification**.
5. **System: document intake.** Each PDF is read and classified *by its content*. A small chip row appears: `nimbus_gst_certificate.pdf → GST Registration Certificate ✓` etc.
6. **System: live run view.** Five stage panels appear one after another (0.6 s pacing if "Demo pacing" is on):
   - Each panel header: stage number + name + summary (`4 passed`, or `1 failed · 1 warning`) + elapsed ms.
   - Inside: one row per check, `✅ / ⚠️ / ❌ / ℹ️  Check name: detail`.
   - A panel with a failure ends red; a panel with only warnings ends amber; otherwise green.
7. **System: decision.** `decide()` runs, and the **Decision card** appears:
   - Big status pill **APPROVED** (green) · queue "Ready for vendor master" · risk bar 0/100 Low · headline.
8. Below the card, 3 tabs: **📧 Vendor email** · **📝 Internal note** · **🧾 Raw record (JSON)**.
9. **System: persist.** The run is saved to SQLite as version 1 under `VS-2026-101`. Toast: "Saved as run #N (v1)".
10. Analyst clicks **Dashboard** in the sidebar → sees KPIs updated and the run at the top of the history.

**End state:** vendor approved, approval email in the outbox, full audit record stored.

---

## Flow B: Submission needs fixes (Pending → Awaiting vendor)

1–6. Same as Flow A with scenario *"02 · Cross-field inconsistencies"*.
7. Live run view: the **Identity** stage turns red with 2 failures (PAN in GSTIN is one character off; GSTIN state is Karnataka but the address is Maharashtra); **Documents** shows the PAN card disagreeing with the form PAN.
8. Decision card: **PENDING** (amber) · queue "Awaiting vendor" · risk 36 Medium · "3 item(s) the vendor needs to fix".
9. The Vendor email tab shows a numbered list of 3 *specific* asks, e.g. "Your GSTIN is registered in Karnataka (state code 29) but your address is in Maharashtra… please share the GSTIN for your Maharashtra registration (it should start with 27)…"
10. The run is saved as v1 of `VS-2026-102`. It appears in the Dashboard **Work queue** under "Awaiting vendor".

---

## Flow C: Resubmission (version 2 and behavioural check)

1. The vendor "replies". In the demo, the analyst loads scenario *"05 · Resubmission with bank swap"* (same ref `VS-2026-102`).
   - Alternative real path: on the Dashboard queue, the analyst clicks **"Resubmit"** on a pending item → the form opens prefilled with that version's data → edits fields → runs.
2. Before running, a banner shows: **"↻ Resubmission detected: this will be v2 of VS-2026-102 (v1 was PENDING · Awaiting vendor)."**
3. Clicks **▶ Run verification**.
4. Live run view: Identity, Bank and Documents now **all pass** (PAN fixed, Maharashtra GSTIN, new cheque matches the new account).
5. The **Fraud** stage shows:
   - ℹ️ "Resubmission v2 vs v1: changed bank.account_number, bank.bank_name, bank.ifsc, gstin, pan"
   - ❌ "Bank account changed (441705001122 → 021963700004412) although the previous review never asked for bank changes"
6. A **diff table** renders under the run view: field · v1 value · v2 value · whether the change was requested (✅ requested / ⚠️ unrequested).
7. Decision card: **PENDING** · queue **Compliance review** · risk 35 · fraud signal badge.
8. Vendor email = a neutral "under review, we may call you on the number originally registered" (does **not** tip off the vendor).
   Internal note = "Unrequested bank change mid-onboarding: classic account-takeover / BEC pattern. Hold. Verify by calling back on the ORIGINAL number on file (9822012345)…"
9. Saved as v2. The work queue now shows `VS-2026-102` under Compliance review (v1 is no longer in the queue; it's superseded).

---

## Flow D: Audit / review a past run

1. Analyst opens **Dashboard** → scrolls to **Run history** (table: run #, time, ref, version, vendor, status, queue, risk, headline).
2. Filters by status (multiselect) or searches by vendor / ref.
3. Selects a run (selectbox "Open run #…") → navigates to **Run detail**.
4. Run detail shows: decision card, all checks grouped by stage (static, not animated), documents with extracted fields, the submission as a table, the vendor email, the internal note, and **version history for this ref** (all versions with status, each openable).
5. **Outbox** page: every generated vendor email newest-first. Each item shows To, Subject, status pill and body in an expander, plus a "Copy" code block.

---

## Flow E: Reset before a demo

1. Sidebar → **Settings** expander → **Reset demo data** button → confirm checkbox "Yes, delete all runs".
2. The system clears the `runs` table → toast "Demo data cleared" → the dashboard shows the empty state ("No runs yet. Load a demo scenario on Submit & Verify").

---

## Settings (sidebar, all pages)

| Control | Default | Effect |
|---|---|---|
| Demo pacing | ON | 0.6 s pause after each stage so viewers can follow |
| Polish email with the same model | OFF | Available when the OpenRouter API key is configured; suggestion remains separate from the deterministic email |
| Reset demo data | | Flow E |

---

## Error and empty states (must handle)

| Situation | Behaviour |
|---|---|
| Run clicked with no documents | Pipeline still runs; the document checks fail as blockers (that's the correct behaviour, not a crash) |
| Uploaded file isn't a readable PDF | `extract_text` returns "" → classified `unknown` → warning row "Couldn't recognise 'x.pdf'" |
| Required field blank or document slot empty | Run button stays disabled and the page lists what needs to be completed |
| Dashboard with zero runs | Friendly empty state, no charts |
| OpenRouter is unavailable or rate-limited | Show the provider error and keep the template email; `polished_by = template` |
| Same scenario loaded twice | Second run becomes v2 of the same ref (correct; to re-demo from scratch, reset first) |
