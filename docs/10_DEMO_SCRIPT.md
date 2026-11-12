# 10 · Demo Script, Video & Interview Prep

## Part 1: The 5-minute video (hard cap 5:00)

**Setup before recording:** reset demo data · demo pacing ON · browser at 110% zoom · close other tabs · Loom on full screen with webcam bubble bottom-right · rehearse twice.

| Time | Screen | What you say (natural, not read out) |
|---|---|---|
| 0:00–0:30 | Submit page, empty | "Before a company pays a vendor, someone has to verify they're real and that the money goes to the right account. Today that's an analyst comparing PDFs by hand, and the dangerous submissions are the ones that look fine field by field. VendorGuard runs every submission through 26 checks in 5 stages and returns approved, pending or rejected, with the reasoning and the message back to the vendor." |
| 0:30–1:20 | Load #1 Happy path → Run | "Clean submission. Watch the stages: intake, identity, where it checks the PAN *inside* the GSTIN, bank, documents (it reads each PDF and classifies it by content, not filename), then fraud screening against our vendor master. Approved, risk zero. Note the bank name said 'PVT. LTD.' and the legal name says 'Private Limited'. Name normalisation handles that, so it doesn't create a false alarm." |
| 1:20–2:20 | Load #2 Cross-field → Run | "This one passes any field-by-field validator. The PAN is well-formed; the GSTIN checksum is valid. But the PAN inside the GSTIN is one character off, and it uses the PAN card PDF to work out which side has the typo. And the GSTIN is Karnataka's while the address is in Maharashtra. GST is state-specific, so it tells the vendor exactly which state code to look for. Pending, awaiting vendor. Here's the email: three specific asks, nothing vague." → open Vendor email tab |
| 2:20–3:20 | Load #5 Resubmission → Run | "Now the vendor resubmits. The banner shows it's v2. Identity, bank, documents: everything passes now, including a new cheque. But the fraud stage catches that the bank account changed, and we never asked for that. This is the business-email-compromise pattern: an attacker in the vendor's inbox 'fixes' the form and redirects payments. So it goes to compliance review, not approval. The vendor gets a neutral message, and the internal note says to call back on the *original* number, because the new contact details might be the attacker's." → open Changes tab, then Internal note |
| 3:20–4:10 | Load #3 Third-party bank → Run | "Genuine company, genuine documents, but the account belongs to 'Kaveri Traders', and our vendor master says that exact account already gets paid as vendor V-1042. Two independent fraud signals: rejected. Compare what the vendor sees, a generic 'account must be in your name', with what compliance sees, the V-1042 link. We never tip off a fraudster." → flip between tabs |
| 4:10–4:45 | Dashboard | "Everything's audited: every run, every version. KPIs, the status split, top failing checks (which tells procurement where vendors struggle), and the work queue split by who needs to act: the vendor or compliance." |
| 4:45–5:00 | Dashboard | "Design choice: rules make the decisions, because a checksum shouldn't depend on a model's opinion, and a decision has to be auditable. The LLM is optional and only polishes email tone, behind a guardrail. Runs fully offline, zero cost. Thanks." |

If short on time: drop #3 from the video (keep it for the live interview).

---

## Part 2: Live interview run order

1. **Reset** demo data (sidebar) at the start, so the dashboard is clean.
2. #1 Happy path → APPROVED
3. #2 Cross-field → PENDING (Awaiting vendor)
4. #5 Resubmission → PENDING (Compliance review) ⭐ the moment to slow down
5. #3 Third-party bank → REJECTED
6. #4 Wrong documents → PENDING (show the doc chip "named like a cheque, reads as PAN card")
7. #6 Proprietorship → APPROVED ("the rules aren't blunt")
8. Dashboard → Run detail of #5 (version history) → Outbox
9. **Offer:** "Want to break it? Give me any change and I'll run it live." Good live tweaks to have ready:
   - Change one character of a GSTIN → checksum failure naming the expected character
   - Set entity type to Proprietorship on #1 → PAN_TYPE blocker (C-type PAN)
   - Blank out IFSC → REQ_FIELDS + IFSC blockers

**Backup plan:** if the cloud app is asleep or slow, run locally (`streamlit run app.py`). Have the local app already open in another tab. Have a 30-second screen recording of each scenario as a last resort.

---

## Part 3: Questions they'll likely ask, with answers

**"Why not just use an LLM for the whole thing?"**
Three reasons. Correctness: a GSTIN checksum has one right answer, and a model can only be worse at it. Auditability: in finance, "the model thought so" isn't an audit trail, and every decision here traces back to a named rule and evidence. Cost and reliability: it runs offline with zero cost and returns the same answer every time. I use the LLM where language is the actual problem (email tone), and even there with a guardrail that falls back to the template if any ID gets dropped.

**"Where would AI add the most value next?"**
Extraction from messy, scanned, non-standard documents, with confidence scores, routing low-confidence extractions to a human. And using reviewer overrides as feedback to tune thresholds.

**"How did you pick the thresholds (88/70 for names)?"**
I tuned them on realistic variants: "PVT. LTD." vs "Private Limited" scores 100 after normalisation; an unrelated company scores around 25. Between 70 and 88 is the ambiguous band, so we ask instead of deciding. In production I'd tune on historical decisions, measuring false approvals vs false pendings, and bias toward false pendings because they cost an email while a false approval costs money.

**"Why is the bank swap pending and not rejected?"**
It could be legitimate; companies do change banks. The right control is out-of-band verification on a channel the attacker doesn't control (the original phone number). That's a human step, so it goes to compliance review.

**"Why don't you tell the vendor the account belongs to another vendor?"**
That confirms to a fraudster exactly which signal tripped, and leaks another vendor's data. The vendor gets a policy-level reason; compliance gets the specifics.

**"What happens with 1,000 vendors a month?"**
The pipeline is about 10 ms of compute per submission, so throughput isn't the issue; reviewer time is. Approved ones need zero touches, and the queue split means compliance only sees the fraud-flagged ones. At scale: a background worker queue, Postgres instead of SQLite, and live API adapters with caching.

**"What's the business case?"**
Say 20–40 minutes of analyst time per vendor today, plus a few email rounds. Clean submissions now need zero touches; problem ones get a precise first email instead of vague back-and-forth. The bigger number is fraud avoided: a single redirected payment can be lakhs, which dwarfs the analyst time.

**"What would you change in v2?"**
Penny-drop and GSTN-active adapters, a vendor portal with magic-link resubmission, OCR plus LLM extraction, sanctions screening, and an override feedback loop. (See `08` §E.)

**"What was hardest?"**
Deciding severities, not coding. The same surface symptom (PAN mismatch) is a typo at distance 1 and an identity problem at distance 2. Getting that nuance right is what keeps the false-reject rate down.

**"What assumptions did you make?"**
Indian domestic vendors, GST-registered, digital PDFs, the standard 3-document pack, payment only to own-name accounts with the proprietorship exception, and a preference for false pendings over false approvals. All written down in `docs/08`.
