# 08 · Assumptions & Design Decisions

The brief says: *"treat ambiguity as part of the exercise. Make an assumption, note it somewhere you can reference in the live pitch, and move on."* This is that place. Each entry: the assumption, why, and what changes if it's wrong.

---

## A. Business assumptions

| # | Assumption | Why | If wrong |
|---|---|---|---|
| A1 | The buying company is **Indian** and onboards **Indian domestic vendors** | Lets the rules go deep (PAN, GSTIN, IFSC) instead of shallow-global; Zamp works with Indian businesses | Add country rule packs (VAT/IBAN/SWIFT); the stage structure stays identical |
| A2 | Every vendor is **GST-registered** | True for most B2B vendors above the turnover threshold; keeps v1 focused | Add a "Not GST-registered" checkbox → require a GST non-registration declaration document instead |
| A3 | Required documents = **GST certificate, PAN card, cancelled cheque** | The standard minimum KYC pack in Indian procurement | Required-doc list is one constant; MSME / incorporation certificates can be added as optional |
| A4 | The vendor is paid **only** into an account in its own legal name (proprietorship exception) | Standard AP control; third-party payments are the top fraud vector | The policy is one threshold block in `ACCOUNT_NAME` |
| A5 | An existing vendor re-registering is a **change request**, not a new onboarding | Prevents duplicate vendor records (a common duplicate-payment source) | Route to an "update vendor" flow |
| A6 | Procurement prefers **false pendings over false approvals** | A pending costs an email; a bad approval costs money | Thresholds (88/70 names, 90 cert name, risk 30) are tunable constants |
| A7 | The vendor fills the form themselves (self-service portal); procurement reviews only exceptions | That's where automation saves time | Same engine works for analyst-entered data |

## B. Data assumptions

| # | Assumption | Why | If wrong |
|---|---|---|---|
| B1 | Digital PDFs use local extraction; optional OpenRouter vision can inspect scanned PDFs | Keeps the core offline while enabling the requested video feature | Scanned/model-only values stay in Compliance review until a human confirms the original; free provider is synthetic-data-only |
| B2 | GST certificates follow the **REG-06** layout | It's the government standard | Fingerprints and regexes are isolated in `documents.py` |
| B3 | The **vendor master is the source of truth** for existing vendors and is a CSV export | Simplest integration; every ERP can export one | Swap for an ERP API read |
| B4 | A **submission reference** identifies a vendor's application across resubmissions | Mirrors how a portal would track an application | Could key on PAN instead |
| B5 | The IFSC → bank mapping by **4-letter prefix** is enough for v1 | The prefix identifies the bank deterministically | Load Razorpay's open IFSC dataset for branch-level validation |
| B6 | All test data is **synthetic** but structurally valid (real checksums, real state codes, real bank prefixes) | No real PII; the logic stays meaningful | |

## C. Product & technical decisions

| # | Decision | Alternatives considered | Why this |
|---|---|---|---|
| C1 | **Rules decide, LLM assists** | LLM-as-judge for everything | OpenRouter classification, field candidates, and score are shown for review; local extraction supplies rule inputs, and scans or conflicts require human review |
| C2 | **Severity-based outcome** (warn/blocker/review/reject) instead of a pure score threshold | Weighted score only | A score can't express "one fraud signal outweighs ten typos." Severity gives the status; the score gives a ranking |
| C3 | **Three-way status with sub-queues** | Binary approve/reject | The brief asks for approved/pending/rejected; queues tell *who* acts next (vendor vs compliance) |
| C4 | **Classify documents by content, not filename** | Trust upload slots or filenames | Wrong-document uploads are a stated pain point; filenames lie |
| C5 | **Never reveal fraud reasoning to the vendor** | Full transparency | Telling a fraudster which signal tripped teaches them to evade it. Internal note vs vendor email are separate artefacts |
| C6 | **Bank change on resubmission → Compliance review, not Reject** | Auto-reject | It might be legitimate (a company changing banks). The right control is out-of-band verification on the original number, which only a human can do |
| C7 | **Append-only audit log** (new row per run and version) | Update in place | Auditors need to see what was submitted when, and what the system decided at that moment |
| C8 | **Streamlit** | Next.js, n8n, Retool | One language, the live status view is native, one-command deploy, free hosting |
| C9 | **Offline-first** | Call live government APIs | A live demo can't depend on third-party uptime; v1 must cost ₹0. Adapters can be added at the same check points |
| C10 | **Hamming distance 1 between PAN and GSTIN-embedded PAN = typo; ≥2 = different entity** | Any mismatch = reject | Real submissions have typos; punishing them creates friction. Two or more character differences is no longer plausibly a typo |
| C11 | **Name match thresholds: ≥88 match, 70–88 ask, <70 third party** | Exact match | Banks print names inconsistently (PVT. LTD., M/s, &). Normalisation plus fuzzy matching absorbs that noise |

## C2. Build-time decisions (logged while implementing)

| # | Decision | Why |
|---|---|---|
| I1 | `ACCOUNT_NAME` tests the proprietor match **before** the legal-name match | Scenario 6 has legal_name = proprietor's name, so the legal-name branch passed first and the "valid for a proprietorship" explanation never showed. Outcome is identical (pass either way); only the explanation changes |
| I2 | Phone numbers are compared **after normalisation** in `RESUB_DIFF` / `RESUB_CONTACT_CHANGE` | `+91 98220 12345` → `9822012345` is reformatting, not a contact swap |
| I3 | When a document type is uploaded twice, the **first** upload is used everywhere | `GSTIN_PAN_LINK` used the last PAN card while the document stage used the first |
| I4 | Manually entered submissions get refs starting at `VS-2026-201` | Keeps them clear of the demo scenario refs (101–106), so a manual entry is never mistaken for a resubmission |
| I5 | Entity type sits just above the form, not inside it | Widgets inside `st.form` don't rerun, and the proprietor field must appear as soon as Proprietorship is picked |
| I6 | `.gitattributes` marks `*.pdf` as binary | The synthetic PDFs are ASCII, so git on Windows was treating them as text and rewriting line endings |
| I7 | `REQUESTED_BY` / `classify_changes` live in `engine/pipeline.py` as `09_PLAN.md` says | This keeps the file over the ~300-line guideline; splitting it would mean rewriting the reference engine, which CLAUDE.md forbids |
| I8 | Required fields and the three required document slots disable Run until present | Running an obviously incomplete submission adds no value; populated but invalid values still reach the engine so it can explain the problem |
| I9 | PDF intake is capped at 10 MB, 40 pages, and 300,000 extracted characters | The synchronous local app needs predictable resource use; production still needs isolated parsing and malware scanning |

## D. Known limitations (say them before they're asked)

1. OpenRouter PDF review can inspect scanned pages when explicitly enabled. This v1 does not persist a standalone OCR transcript; visual-only extraction stays in Compliance review until a reviewer confirms it. The free endpoint must only receive synthetic examples.
2. No live verification that the GSTIN is *active* on the GST portal, or that the account holder name matches at the bank (penny-drop). Both are paid or gated APIs; the check points exist for adapters.
3. The cheque's printed holder name is extracted but not yet compared.
4. The dashboard on Streamlit Cloud resets when the app sleeps (ephemeral disk). Locally it persists.
5. Single user, no auth.
6. Thresholds were tuned on 6 scenarios. In production they'd be tuned on historical decisions (precision/recall on known-good vs known-bad vendors).

## E. What I'd build next (v2 roadmap, in priority order)

1. **Penny-drop + GSTN-active adapters**: closes the two biggest verification gaps.
2. **Vendor portal with magic-link resubmission**: prefilled, only failing fields editable.
3. **Production OCR worker** for scanned documents, with page-level confidence and human confirmation below a threshold; OpenRouter's free endpoint is only the synthetic-data demo path.
4. **Sanctions/PEP screening** (OFAC SDN, OpenSanctions).
5. **Feedback loop**: reviewer overrides are logged and used to tune thresholds.
6. **ERP write-back** of approved vendors (SAP / NetSuite / Tally).
7. **Ongoing monitoring**: re-check active vendors monthly (GSTIN cancelled? bank changed?).
