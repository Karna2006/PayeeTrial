# 01 · Product Requirements Document: PayeeTrail

> Zamp · AI Solutions Analyst case study · **PS-2: Vendor onboarding, from submission to approval**
> Owner: Arun Kaarthikeyan · Build window: 1 day · Status: Ready to build

---

## 1. One-liner

**PayeeTrail takes a vendor's onboarding submission (form + documents), cross-checks every field and document against each other and against the existing vendor list, and returns Approved / Pending / Rejected, with the reasoning visible and a ready-to-send message telling the vendor exactly what to fix.**

---

## 2. The problem (in the buyer's words)

Before a company can pay a vendor, procurement has to verify the vendor is real and that the money will land in the right account. Today that's manual:

- A procurement analyst opens each submission, eyeballs PAN, GSTIN and bank details, opens each PDF, and compares by hand.
- Submissions are often incomplete or inconsistent: wrong documents, a GSTIN from a different state, a bank account in someone else's name.
- The truly dangerous ones **look fine field by field**. The inconsistency only shows when you cross-reference: the PAN inside the GSTIN doesn't match the PAN, or the bank account already belongs to another vendor.
- Follow-up is manual email ping-pong. The audit trail is someone's inbox.
- A bad onboarding means **payment fraud** (money paid into a fraudster's account) or **compliance failure** (GST input credit lost, a vendor that doesn't legally exist).

**Cost of the status quo:** about 20–40 minutes of analyst time per vendor, several back-and-forth emails, days of cycle time, and a fraud risk that depends on how tired the reviewer is.

---

## 3. Target users

| User | What they do | What they need from PayeeTrail |
|---|---|---|
| **Procurement / AP analyst** (primary) | Reviews new vendor submissions | A decision with reasons they can trust in 10 seconds; a queue of what needs them; zero time spent on clean cases |
| **Compliance / finance controller** (secondary) | Owns fraud and audit risk | Fraud signals flagged clearly, nothing auto-approved that shouldn't be, a full audit trail of every run and resubmission |
| **Vendor** (indirect) | Submits details and documents | A clear, specific message: what's wrong, what to send, nothing vague like "documents incomplete" |
| **Interviewer / buyer** (demo audience) | Evaluates the build | To watch the process execute stage by stage and understand every decision without reading code |

---

## 4. MVP feature list (strictly 5)

### F1 · Submission intake
- A web form capturing company, address, contact and bank details, plus multi-file PDF upload (GST certificate, PAN card, cancelled cheque).
- **One-click "Load demo scenario"** that prefills the form and attaches the sample documents (6 scenarios). This is critical for a smooth live demo.

### F2 · Verification pipeline with a live run view
Five stages execute in order, and the UI shows each one as it runs with every check's result:
1. **Intake & completeness**: required fields, email, phone, PIN code
2. **Identity**: PAN format and holder type, GSTIN format and checksum, PAN embedded in GSTIN, GSTIN state vs address
3. **Bank**: IFSC format and bank, account format, account holder name vs legal entity (with the proprietorship exception)
4. **Document cross-check**: classify each upload *by its content* (not filename), extract fields, compare to the form
5. **Duplicate & fraud screening**: existing vendor (same PAN), bank account used by another vendor, unrequested bank change on resubmission

Full rule definitions: `05_RULES_SPEC.md`.

### F3 · Decision engine with explainable output
- Status: **APPROVED / PENDING / REJECTED**
- Queue: *Ready for vendor master · Awaiting vendor · Compliance review · Procurement review · Closed: rejected*
- Risk score 0–100 plus level (Low / Medium / High)
- A one-line headline reason, plus every failed or warned check with its evidence

### F4 · Communication back to the vendor, plus a resubmission loop
- An auto-generated vendor email: numbered, specific asks for Pending; a safe, non-revealing message for Rejected and Compliance review.
- An internal note for the reviewer (fraud context the vendor must *not* see).
- **Resubmission**: the same submission reference becomes version N+1. The diff against the previous version is shown, and behaviour across versions is checked (the bank-swap fraud pattern).

### F5 · Dashboard and audit trail
- KPI tiles (total runs, approval rate, pending, rejected, average risk, average processing time)
- Status split and top failing checks (charts)
- Work queue (everything pending, grouped by queue)
- Full run history; click any run to see its complete record (submission, documents, check results, decision, email, note)
- Outbox (every vendor email generated)

---

## 5. Non-goals: what we are NOT building

These are deliberate. When asked "why not X?" in the interview, the answer is: *scoped out to ship a reliable v1 in one day, and here's how I'd add it.*

| Not building | Why | How v2 would add it |
|---|---|---|
| ❌ Login, auth, user roles | Single-user demo; adds nothing to the decision logic | SSO plus role-based access (analyst vs compliance) |
| ❌ A real vendor-facing portal or magic links | The interviewer plays the vendor via the same form | Tokenised resubmission link that pre-fills from the last version |
| ❌ Actually sending email | Risky in a demo; needs a domain or SMTP | SMTP / Resend / Gmail API; the outbox is already the queue |
| ❌ OCR of scanned / image documents | Digital PDFs prove the logic; OCR adds a day of tuning | Tesseract / PaddleOCR before the same parser |
| ❌ Live government API checks (GSTN portal, NSDL PAN, penny-drop) | Paid / gated APIs; not open-source | Plug-in adapters at the same check points (designed as swap-ins) |
| ❌ Branch-level IFSC lookup | Full dataset not needed for the demo | Razorpay's open IFSC dataset (MIT) as an offline lookup |
| ❌ Sanctions / PEP screening | Out of scope for v1 | OFAC SDN list (free CSV) as a stage-5 check |
| ❌ International vendors (VAT, IBAN, SWIFT) | India-first keeps the rules deep, not wide | Country-aware rule packs; python-stdnum already supports IBAN and VAT |
| ❌ ML / LLM making the decision | Decisions must be deterministic and auditable | LLM stays assistive (message tone, extracting from unusual documents) |
| ❌ Editing vendor master from the UI, ERP integration | Not needed to show the process | Write approved vendors to SAP / Tally / NetSuite via API |
| ❌ Dark mode, mobile layout, i18n, notifications | Cosmetic | Later |
| ❌ Multi-tenant, scaling, async workers, Docker | Single-machine demo | Queue plus workers if volume demands it |

---

## 6. Success criteria (definition of done)

1. All **6 demo scenarios** produce their expected decision every time (see `06_TEST_SCENARIOS.md`).
2. A run completes in **under 3 seconds** (excluding the optional demo pacing).
3. The live run view shows all 5 stages with per-check results; the decision card shows status, queue, risk, headline and reasons.
4. Every non-approved run produces a vendor email whose asks are **specific** (they name the exact field, value and fix).
5. The resubmission of scenario 2 (as scenario 5) is detected as version 2 and routed to Compliance review.
6. The dashboard reflects every run and survives an app restart (SQLite).
7. **Zero paid services.** It runs fully offline on a laptop; it's deployable to Streamlit Community Cloud from a public GitHub repo.
8. A 5-minute demo video is recorded: happy path plus at least 2 edge cases.

---

## 7. Design principles (say these in the interview)

1. **Rules decide, AI assists.** A checksum is right or wrong; it should never be left to a model's opinion. The LLM is used only where language matters (vendor message tone), behind a guardrail that falls back to the template.
2. **Cross-reference beats field validation.** Most tools check that each field is well-formed. The fraud lives *between* fields: the GSTIN vs the PAN, the account holder vs the legal name, version 1 vs version 2.
3. **Severity drives the outcome.** Not every failure is equal: typo → ask the vendor; inconsistency → ask with a precise hint; fraud signal → reject or escalate to a human.
4. **Never tip off a fraudster.** The internal note says "this account belongs to vendor V-1042"; the vendor email never does.
5. **Fix only what's broken.** The vendor gets asked only for failing items; everything verified is kept.
6. **Everything is auditable.** Every run, every version, every check is stored.

---

## 8. Glossary (India-specific terms)

| Term | Meaning |
|---|---|
| **PAN** | Permanent Account Number. A 10-character tax ID (`AAAAA9999A`). 4th char = holder type (C company, P individual, F firm/LLP…). 5th char = first letter of the entity's name (or the surname for individuals). |
| **GSTIN** | GST Identification Number. 15 chars = 2-digit **state code** + **10-char PAN** + entity number + `Z` + **checksum** character. One GSTIN per state per PAN. |
| **IFSC** | Indian Financial System Code. 11 chars identifying a bank branch: 4-letter bank code + `0` + 6-char branch code. |
| **Cancelled cheque** | A cheque marked "CANCELLED", submitted as proof the account exists in the vendor's name. |
| **GST REG-06** | The official GST registration certificate form. |
| **Proprietorship** | A one-person business. Legally the same person as the owner, so a bank account in the owner's personal name is normal. |
| **Penny-drop** | Depositing ₹1 to verify the account holder's name with the bank (paid API; out of scope). |
| **BEC** | Business Email Compromise. A fraudster hijacks or impersonates a vendor to swap bank details. |
| **Vendor master** | The company's list of approved vendors. |
