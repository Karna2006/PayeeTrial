# 03 · Data Schema

Every object that flows through the system, with every field defined. Names here are the exact names to use in code.

```
Submission (JSON) ──┐
Uploaded PDFs ──► ParsedDoc[] ──┤
Vendor master (CSV) ────────────┼──► Pipeline ──► CheckResult[] ──► Decision ──► VendorEmail + InternalNote
Previous run (SQLite) ──────────┘                                                      │
                                                                                       ▼
                                                                                 Run (SQLite row)
```

---

## 1. `Submission`: the input

Stored as JSON. Sample files wrap it as `{"title", "expected", "submission"}`.

```json
{
  "submission_ref": "VS-2026-101",
  "legal_name": "Nimbus Logistics Private Limited",
  "trade_name": "Nimbus Logistics",
  "entity_type": "Private Limited Company",
  "proprietor_name": "",
  "pan": "AAACN4821K",
  "gstin": "29AAACN4821K1ZB",
  "address": {
    "line1": "42, 2nd Cross, Indiranagar",
    "city": "Bengaluru",
    "state": "Karnataka",
    "pincode": "560038"
  },
  "contact": {
    "name": "Priya Raman",
    "email": "accounts@nimbuslogistics.in",
    "phone": "+91 98450 12345"
  },
  "website": "https://nimbuslogistics.in",
  "bank": {
    "account_holder": "NIMBUS LOGISTICS PVT. LTD.",
    "account_number": "50200012345678",
    "ifsc": "HDFC0001234",
    "bank_name": "HDFC Bank"
  },
  "documents": ["nimbus_gst_certificate.pdf", "nimbus_pan.pdf", "nimbus_cancelled_cheque.pdf"]
}
```

| Field | Type | Required | Rules / notes |
|---|---|---|---|
| `submission_ref` | str | auto | Format `VS-YYYY-NNN`. **Same ref = resubmission** (new version). New form → generate a new ref |
| `legal_name` | str | ✅ | Registered legal name. For a proprietorship it's the proprietor's name |
| `trade_name` | str | ❌ | Brand / trading-as name |
| `entity_type` | enum | ✅ | `Private Limited Company` · `Public Limited Company` · `LLP` · `Partnership Firm` · `Proprietorship` |
| `proprietor_name` | str | ✅ if Proprietorship | Hidden in the UI unless Proprietorship is selected |
| `pan` | str(10) | ✅ | Normalised: uppercase, spaces and hyphens stripped |
| `gstin` | str(15) | ✅ | Normalised as above. (v1 assumes every vendor is GST-registered; see Assumptions) |
| `address.line1` / `city` | str | ✅ | |
| `address.state` | enum | ✅ | One of the 36 names in `GST_STATE_CODES` (dropdown) |
| `address.pincode` | str(6) | ✅ | 6 digits, first digit ≠ 0 |
| `contact.name` | str | ✅ | |
| `contact.email` | str | ✅ | |
| `contact.phone` | str | ✅ | Any formatting; the last 10 digits are validated |
| `website` | str | ❌ | Used only for the email-domain consistency signal |
| `bank.account_holder` | str | ✅ | As printed on the bank account |
| `bank.account_number` | str | ✅ | Digits only after normalisation, 9–18 long |
| `bank.ifsc` | str(11) | ✅ | Normalised uppercase |
| `bank.bank_name` | str | ✅ | Free text, compared to the bank implied by the IFSC |
| `documents` | list[str] | ✅ (≥1) | Filenames. In the UI, real uploaded bytes and/or attached sample files |

---

## 2. `ParsedDoc`: one uploaded document after reading

| Field | Type | Notes |
|---|---|---|
| `filename` | str | Original filename (**never** used for classification) |
| `doc_type` | enum | `gst_certificate` · `pan_card` · `cancelled_cheque` · `unknown` |
| `text` | str | Raw text extracted by pypdf |
| `fields` | dict | Extracted values, depending on `doc_type`, see below |
| `warnings` | list[str] | Intake problems such as corrupt/encrypted PDFs, size/page limits, or no selectable text; warnings never count as verification evidence |
| `page_count` | int or null | Page count when the PDF could be safely opened |
| `page_texts` | list[str] | Selectable text by page, kept in memory to verify AI page citations; not persisted as a second transcript |
| `ai_review` | object or null | Optional OpenRouter classification, extracted fields, page evidence, model/version and advisory score; visual-only extraction is marked for human review |
| `sha256` | str | SHA-256 of the exact uploaded file bytes; used to detect byte-identical files renamed before upload |
| `file_size` | int | Uploaded byte count |
| `analyst_review` | object or null | Accepted type/fields, original type/fields, reviewer, timestamp, reason, and confirm/correct action; never replaces `ai_review` |
| `autofill_fields` | list[object] | Source document, extracted field/value, final submitted value, text/OCR source, and cited page/quote for form fields suggested during upload |

**Extracted `fields` per type:**

The document cross-check requires every listed core field before it can pass: GST `gstin`, `legal_name`, `status`; PAN `pan`, `name`; cheque `ifsc`, `account_number`, `account_holder`. A missing value routes the record to analyst review. Different-content documents classified as the same required type also require review; byte-identical uploads are treated as one document for matching.

| doc_type | fields | Extraction pattern (regex on text) |
|---|---|---|
| `gst_certificate` | `gstin`, `legal_name`, `trade_name`, `address`, `status` | `Registration Number: (…15 chars)`, `Legal Name: (…)`, `Trade Name…: (…)`, `Address of Principal Place of Business: (…)`, `Status: (word)` |
| `pan_card` | `pan`, `name` | First `[A-Z]{5}[0-9]{4}[A-Z]` token; `Name: (…)` |
| `cancelled_cheque` | `ifsc`, `account_number`, `account_holder`, `bank_name` | `IFSC Code: (…)`, `A/C No: (digits)`, `For: (…)`, first line containing "Bank" |

**Classification fingerprints** (case-insensitive; count matching keywords, the highest count wins, and **at least 2 hits** are needed, otherwise `unknown`):

| doc_type | keywords |
|---|---|
| `gst_certificate` | `REG-06`, `registration certificate`, `goods and services tax` |
| `cancelled_cheque` | `cancelled`, `pay `, `a/c no`, `ifsc` |
| `pan_card` | `permanent account number`, `income tax department` |

---

## 3. `CheckResult`: the output of one check

| Field | Type | Notes |
|---|---|---|
| `check_id` | str | Stable ID, e.g. `GSTIN_PAN_LINK` (full list in `05_RULES_SPEC.md`) |
| `stage` | enum | `intake` · `identity` · `bank` · `documents` · `fraud` |
| `name` | str | Human label, e.g. "PAN embedded in GSTIN" |
| `status` | enum | `pass` · `fail` · `warn` · `info` |
| `detail` | str | One sentence: what we saw (shown in the run view) |
| `severity` | enum | Matters when status is fail/warn: `warn` · `blocker` · `review` · `reject` · `info` |
| `evidence` | dict | Raw values that justify the result (e.g. `{"gstin_pan": "...", "form_pan": "..."}`) |
| `vendor_ask` | str | What to tell the vendor (empty = tell them nothing about this) |
| `internal_note` | str | What to tell the reviewer (may contain things the vendor must not see) |
| `tags` | list[str] | `fraud-signal`, `risk-signal` |

---

## 4. `Decision`

| Field | Type | Values / logic |
|---|---|---|
| `status` | enum | `APPROVED` · `PENDING` · `REJECTED` |
| `queue` | enum | `Ready for vendor master` · `Awaiting vendor` · `Compliance review` · `Procurement review` · `Closed: rejected` |
| `headline` | str | The single most important reason (first reject, else first review, else blocker count, else "all passed") |
| `risk_score` | int 0–100 | Σ weights of failed checks by severity + 5 × number of warnings, capped at 100 |
| `risk_level` | enum | `Low` (< 20) · `Medium` (20–49) · `High` (≥ 50) |
| `fraud_signals` | list[str] | check_ids of failed checks tagged `fraud-signal` |
| `n_pass`, `n_fail`, `n_warn` | int | Counts for the UI |

**Severity weights:** `warn` = 5 · `blocker` = 12 · `review` = 35 · `reject` = 45

**Decision precedence (first match wins):**
1. any failed check with severity `reject` → **REJECTED** / `Closed: rejected`
2. any failed check with severity `review` → **PENDING** / `Compliance review`
3. any failed check with severity `blocker` → **PENDING** / `Awaiting vendor`
4. no failures but risk_score ≥ 30 (stacked warnings) → **PENDING** / `Procurement review`
5. otherwise → **APPROVED** / `Ready for vendor master`

---

## 5. `VendorEmail`

| Field | Type | Notes |
|---|---|---|
| `to` | str | contact.email |
| `subject` | str | Depends on status (see `05_RULES_SPEC.md` §7) |
| `body` | str | Plain text |
| `asks` | list[str] | `vendor_ask` of every failed check that has a non-empty ask, in pipeline order |
| `polished_by` | str | `template` or `openrouter:<model>` |

`InternalNote` is a plain string: decision line + headline + `[CHECK_ID] internal_note` for every failed or warned check that has a note.

---

## 6. `Run`: SQLite table `runs` (file `data/runs.db`)

Every pipeline execution = one row. **Never updated, only inserted** (audit trail).

| Column | Type | Notes |
|---|---|---|
| `run_id` | INTEGER PK AUTOINCREMENT | |
| `submission_ref` | TEXT NOT NULL | Groups versions |
| `version` | INTEGER NOT NULL | 1 for first, previous max + 1 for resubmissions |
| `created_at` | TEXT | ISO timestamp, seconds precision |
| `vendor_name` | TEXT | legal_name |
| `status` | TEXT | Decision.status |
| `queue` | TEXT | Decision.queue |
| `risk_score` | INTEGER | |
| `headline` | TEXT | |
| `duration_ms` | REAL | Pipeline compute time (excluding demo pacing) |
| `submission` | TEXT (JSON) | Normalised submission |
| `documents` | TEXT (JSON) | JSON records include filename, doc type, fields, warnings, page count, file hash/size, optional AI review, and optional analyst review |
| `results` | TEXT (JSON) | List of CheckResult dicts |
| `decision` | TEXT (JSON) | Decision dict |
| `email` | TEXT (JSON) | VendorEmail dict |
| `internal_note` | TEXT | |

`analyst_reviews` is a separate append-only table linked to `run_id`. Each event stores reviewer, timestamp, reason, accepted document values, rerun checks, decision, and message. Hydrated reads expose the original automated decision alongside the latest analyst-reviewed result; the original `runs` row and its submission version are not overwritten.

**Queries needed:**
- `latest(ref)`: newest version for a ref (to detect resubmission and supply `previous`)
- `all_runs()`: dashboard and history, newest first
- `get_run(run_id)`: run detail page
- `reset()`: delete all rows (Settings → "Reset demo data")

> The *current state* of a submission = its latest version. The work queue shows only the latest version per ref whose status is PENDING.

---

## 7. `VendorMaster`: `data/vendor_master.csv`

Existing approved vendors; read-only in v1. Loaded with `dtype=str` (preserves leading zeros).

| Column | Example |
|---|---|
| `vendor_id` | `V-1042` |
| `legal_name` | `Kaveri Traders` |
| `pan` | `AAFFK2210D` |
| `gstin` | `07AAFFK2210D1Z1` |
| `bank_account` | `34567890123` |
| `ifsc` | `SBIN0001789` |
| `status` | `Active` |

Contains 6 vendors (V-1001, V-1017, V-1029, V-1042, V-1056, V-1063). **V-1042 Kaveri Traders** is the one scenario 3 collides with.

---

## 8. Reference data (constants in code)

| Constant | Content |
|---|---|
| `GST_STATE_CODES` | `"01"`→Jammu and Kashmir … `"29"`→Karnataka, `"27"`→Maharashtra, `"33"`→Tamil Nadu, `"07"`→Delhi, `"32"`→Kerala … `"38"`→Ladakh (36 entries; 25 merged into 26, 28 = pre-2014 Andhra Pradesh and 97 = Other Territory are not used) |
| `PAN_HOLDER_TYPES` | C Company · P Individual · F Firm/LLP · H HUF · A AOP · T Trust · B BOI · L Local Authority · J Artificial Juridical Person · G Government |
| `ENTITY_EXPECTED_PAN_TYPE` | Pvt Ltd → C · Public Ltd → C · LLP → F · Partnership → F · Proprietorship → P |
| `IFSC_BANKS` | SBIN State Bank of India · HDFC HDFC Bank · ICIC ICICI Bank · UTIB Axis Bank · KKBK Kotak · PUNB PNB · BARB Bank of Baroda · CNRB Canara · UBIN Union Bank · IDIB Indian Bank · YESB Yes Bank · INDB IndusInd · IDFB IDFC First · FDRL Federal Bank · BKID Bank of India · IOBA Indian Overseas Bank · MAHB Bank of Maharashtra · RATN RBL Bank |
| `FREE_EMAIL_DOMAINS` | gmail.com, yahoo.com, yahoo.co.in, outlook.com, hotmail.com, rediffmail.com, protonmail.com, icloud.com, live.com |

---

## 9. Folder layout

```
vendorguard/
├── app.py                     # Streamlit entry point (routing only, thin)
├── ui/                        # one file per page + shared components
│   ├── components.py          # status pill, risk bar, check row, decision card
│   ├── page_submit.py         # form + live run view + decision
│   ├── page_dashboard.py      # KPIs, charts, queue, history
│   ├── page_run_detail.py     # full record of one run
│   └── page_outbox.py         # generated vendor emails
├── engine/                    # pure logic, no Streamlit imports
│   ├── validators.py          # PAN/GSTIN/IFSC/name helpers + reference data
│   ├── documents.py           # PDF → ParsedDoc
│   ├── pipeline.py            # 5 stages + decide()
│   ├── messages.py            # vendor email + internal note + optional OpenRouter polish
│   └── store.py               # SQLite audit trail
├── scripts/make_samples.py    # generates samples/ + data/vendor_master.csv
├── samples/                   # 6 scenario JSONs + docs/*.pdf (17 PDFs)
├── data/vendor_master.csv     # existing vendors
├── data/runs.db               # created at runtime (gitignored)
├── tests/test_scenarios.py    # pytest: each scenario → expected status
├── .streamlit/config.toml     # theme
├── requirements.txt
├── CLAUDE.md / AGENTS.md      # agent rulebook
└── docs/                      # this planning pack
```
