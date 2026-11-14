# 05 · Rules Specification

Every check, its exact logic, its severity, and the exact wording of what we tell the vendor and the reviewer. This is the brain of the product. Code must match this document; if you change a rule, change this file in the same commit.

**Status legend:** ✅ pass · ❌ fail · ⚠️ warn · ℹ️ info
**Severity legend (on failure):** `warn` noted only · `blocker` vendor can fix → PENDING/Awaiting vendor · `review` human must look → PENDING/Compliance review · `reject` hard stop → REJECTED

---

## 0. Normalisation (before any check)

| Field | Normalisation |
|---|---|
| `pan`, `gstin`, `bank.ifsc`, `bank.account_number` | remove spaces and hyphens, uppercase |
| `contact.phone` | keep digits only, take the last 10 (applied when validating and when comparing versions; the stored value keeps the vendor's formatting) |
| Names (for comparison only, never stored) | see §8 name normalisation |

---

## 1. Stage: INTAKE & COMPLETENESS

| ID | Check | Logic | Outcome | Severity | Vendor ask | Internal note |
|---|---|---|---|---|---|---|
| `REQ_FIELDS` | Required fields present | Every field in the required list (Data Schema §1) is non-blank. If entity_type = Proprietorship, `proprietor_name` is also required | ❌ if any missing (list them all in one result) | blocker | "Please fill in: {comma-separated labels}." | |
| `EMAIL` | Contact email | (a) contains `@`, else ❌; (b) domain in FREE_EMAIL_DOMAINS **and** entity ≠ Proprietorship → ⚠️; (c) website given and its domain ≠ email domain → ⚠️; else ✅ | ❌ / ⚠️ / ✅ | (a) blocker, (b)(c) warn | (a) "Please share a valid contact email address." | (b) "Free-mail domain on a company submission. Weak signal on its own; weigh with other checks." tag `risk-signal` · (c) "Domain mismatch, often benign (group email domains)." |
| `PHONE` | Contact phone | Last 10 digits: length 10 and first digit ∈ {6,7,8,9} | ❌ / ✅ | blocker | "Please share a valid 10-digit mobile number for verification calls." | |
| `PINCODE` | PIN code | 6 digits, first ≠ 0 (only emitted on failure) | ❌ | blocker | "Please correct the PIN code of your registered address." | |

---

## 2. Stage: IDENTITY (PAN + GSTIN)

| ID | Check | Logic | Outcome | Severity | Vendor ask | Internal note |
|---|---|---|---|---|---|---|
| `PAN_FORMAT` | PAN format | Matches `^[A-Z]{5}[0-9]{4}[A-Z]$` | ❌ / ✅ | blocker | "Your PAN appears malformed. Please re-enter it exactly as on the PAN card." | |
| `PAN_TYPE` | PAN holder type matches entity type | (only if PAN valid) `pan[3]` must equal ENTITY_EXPECTED_PAN_TYPE[entity_type] | ❌ / ✅ | blocker | "The PAN you provided belongs to a {holder type}, but you registered as a {entity_type}. Please provide the PAN of the business entity." | |
| `PAN_INITIAL` | PAN name initial | (only if PAN valid) `pan[4]` vs first letter of: surname (last word of proprietor_name) if holder type P; else legal_name with suffixes (pvt/ltd/llp/co/corp/inc) removed. Only emitted on mismatch | ⚠️ | warn | (none) | "Soft signal: PAN may belong to another entity. Covered by GSTIN link + PAN card checks." |
| `GSTIN_VALID` | GSTIN format + checksum | Format `^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`, then checksum (§9). **If this fails, stop the identity stage here** (later identity checks need a valid GSTIN) | ❌ / ✅ | blocker | Format: "Your GSTIN appears malformed. Please re-enter it exactly as on your GST certificate." · Checksum: "Your GSTIN fails the checksum, which usually means a typo. Please re-check it against your GST certificate." Detail must name the expected vs actual check character | |
| `GSTIN_PAN_LINK` ⭐ | PAN embedded in GSTIN | `emb = gstin[2:12]`; compare to `pan` by Hamming distance. **d = 0** ✅ · **d = 1** ❌ blocker (typo). If the PAN-card PDF's PAN == emb, append the hint · **d ≥ 2** ❌ reject (different legal entity) | ✅ / ❌ | d=1 blocker · d≥2 **reject** + `fraud-signal` | d=1: "Your PAN ({pan}) and the PAN inside your GSTIN ({emb}) differ by one character.{hint} Please confirm the correct PAN." hint = " Your PAN card shows {card}, matching the GSTIN, so the form entry looks like a typo." · d≥2: "The GST registration you provided belongs to a different legal entity than your PAN. We can only onboard a vendor whose GSTIN and PAN belong to the same entity." | d≥2: "Identity mismatch: GSTIN and PAN belong to different entities. Possible borrowed GSTIN." |
| `GSTIN_STATE` ⭐ | GSTIN state matches address | `GST_STATE_CODES[gstin[:2]]` vs `address.state` (case-insensitive) | ❌ / ✅ | blocker | "Your GSTIN is registered in {gst_state} (state code {code}), but your address is in {addr_state}. GST is state-specific: please share the GSTIN for your {addr_state} registration (it should start with {expected_code}), or update the address if you'll invoice from {gst_state}." | |

> ⭐ = headline checks to demo. These are the "subtle inconsistencies only visible when you cross-reference fields" from the brief.

---

## 3. Stage: BANK

| ID | Check | Logic | Outcome | Severity | Vendor ask | Internal note |
|---|---|---|---|---|---|---|
| `IFSC` | IFSC format | `^[A-Z]{4}0[A-Z0-9]{6}$`. On pass, the detail names the bank from IFSC_BANKS | ❌ / ✅ | blocker | "Your IFSC code looks incorrect. Please check it on your cheque." | |
| `IFSC_BANK` | IFSC matches stated bank | name_similarity(IFSC_BANKS[ifsc[:4]], bank.bank_name) < 70 → ⚠️ (only emitted on mismatch; skipped if prefix unknown) | ⚠️ | warn + `risk-signal` | (none) | "Bank name and IFSC disagree. Data-entry slip or details pasted from someone else's account." |
| `ACCOUNT_NO` | Account number format | digits only, length 9–18 (only emitted on failure) | ❌ | blocker | "Your bank account number looks incorrect. Please re-check it." | |
| `ACCOUNT_NAME` ⭐ | Account holder = legal entity | `sim = name_similarity(account_holder, legal_name)` · **if** entity = Proprietorship and name_similarity(account_holder, proprietor_name) ≥ 88 → ✅ (detail explains why it's valid; tested first so the explanation shows even when legal_name is also the proprietor's name) · **else if sim ≥ 88** ✅ · **else if sim ≥ 70** ❌ blocker · **else** ❌ reject | ✅ / ❌ | 70–88 blocker · < 70 **reject** + `fraud-signal` | 70–88: "The bank account name ('{holder}') doesn't exactly match your registered name ('{legal}'). Please confirm the account belongs to your business, or share a cancelled cheque showing the registered name." · <70: "We can only make payments to a bank account held in your registered business name. Third-party accounts can't be accepted." | <70: "Third-party bank account. The #1 vendor payment-fraud pattern." |

Thresholds 88 / 70 were tuned on the sample set; examples: "NIMBUS LOGISTICS PVT. LTD." vs "Nimbus Logistics Private Limited" = 100 after normalisation; "Kaveri Traders" vs "Sunrise Office Supplies Private Limited" = 26.7.

---

## 4. Stage: DOCUMENT CROSS-CHECK

Required document types: `gst_certificate`, `pan_card`, `cancelled_cheque`. Classification is **by content**, never by filename (see Data Schema §2).

| ID | Check | Logic | Outcome | Severity | Vendor ask |
|---|---|---|---|---|---|
| `DOC_UNKNOWN` | Recognise '{filename}' | One result per upload classified `unknown` | ⚠️ | warn | (none) |
| `DOC_AI_REVIEW` | Review AI extraction for '{filename}' | Optional OpenRouter review: local PDF text absent, provider unavailable for an image-only PDF, local and AI classifications disagree, or required local/AI fields differ or are missing | ❌ | review | (none) | "Confirm document type and extracted values against the original PDF before approving. AI document scoring is advisory." |
| `DOC_GST_CERTIFICATE` / `DOC_PAN_CARD` / `DOC_CANCELLED_CHEQUE` | {Type} provided | At least one upload classified as that type. Detail on failure lists what *was* received, e.g. "(GST Registration Certificate, PAN Card, PAN Card)" | ❌ / ✅ | blocker | "Please upload your {type}." + if some type was uploaded twice: " We received {type} twice; one of the uploads may have been the wrong file." |
| `GST_DOC_MATCH` ⭐ | GST certificate matches form | Problems list: (a) cert gstin ≠ form gstin; (b) name_similarity(cert legal_name, form legal_name) < 90; (c) cert status ∈ {cancelled, suspended, inactive}. Any problem → ❌ | ❌ / ✅ | blocker | "The GST certificate you uploaded doesn't match your submission ({problems joined by '; '}). Please upload the certificate for {legal_name} with GSTIN {gstin}." |
| `PAN_DOC_MATCH` | PAN card matches form | card pan ≠ form pan → ❌. If card pan == gstin[2:12], add the typo hint | ❌ / ✅ | blocker | "Your PAN card shows {card} but the form says {pan}.{ hint} Please correct the PAN on the form." hint = " It matches the PAN inside your GSTIN, so the form entry is likely a typo." |
| `CHEQUE_MATCH` | Cancelled cheque matches bank details | Problems: cheque account ≠ form account; cheque IFSC ≠ form IFSC | ❌ / ✅ | blocker | "Your cancelled cheque doesn't match the bank details on the form ({problems}). Please correct one of them." |

> v1 limitation: the cheque's printed account-holder name is extracted but not yet compared (the form's holder name is already checked by `ACCOUNT_NAME`). Easy v2 addition.

---

## 5. Stage: DUPLICATE & FRAUD SCREENING

| ID | Check | Logic | Outcome | Severity | Vendor ask | Internal note |
|---|---|---|---|---|---|---|
| `DUP_VENDOR` | Not already an existing vendor | form pan ∈ vendor_master.pan | ❌ / ✅ | **reject** | "You're already registered with us as a vendor. If your details have changed, please use the vendor-update process instead." | "Duplicate of {vendor_id}. Route to change-request, not new onboarding." |
| `DUP_BANK` ⭐ | Bank account not used by another vendor | form account_number ∈ vendor_master.bank_account **where pan ≠ form pan** | ❌ / ✅ | **reject** + `fraud-signal` | **(empty: never disclose)** | "Bank account shared with existing vendor {id} ({name}). Do NOT disclose this to the submitter. Investigate for collusion / shell vendor." |
| `RESUB_DIFF` | Resubmission vN vs vN-1 | Only if a previous version exists. Flatten both submissions (dot paths, excluding `documents`, `submission_ref`), list changed keys | ℹ️ | info | | |
| `RESUB_BANK_CHANGE` ⭐ | Bank details stable across resubmission | Only on resubmission. `bank_changed` = account_number or ifsc changed. `asked_bank` = previous version had any failed check in stage `bank` or `CHEQUE_MATCH`. bank_changed **and not** asked_bank → ❌ · bank_changed and asked_bank → ✅ "changed in response to an earlier request" | ❌ / ✅ | **review** + `fraud-signal` | **(empty: send the neutral review email)** | "Unrequested bank change mid-onboarding: classic account-takeover / BEC pattern. Hold. Verify by calling back on the ORIGINAL number on file ({old phone}), never on contact details from the new submission." |
| `RESUB_CONTACT_CHANGE` | Contact details stable | Both phone **and** email changed vs previous version | ⚠️ | warn + `risk-signal` | | "Both contact channels swapped. Verify through original channel." |

### Requested vs unrequested change (for the diff table in the UI)
A changed field counts as **requested** if the previous version had a failed check that maps to it:

| Field changed | Requested if previous version failed any of |
|---|---|
| `pan` | PAN_FORMAT, PAN_TYPE, GSTIN_PAN_LINK, PAN_DOC_MATCH |
| `gstin` | GSTIN_VALID, GSTIN_PAN_LINK, GSTIN_STATE, GST_DOC_MATCH |
| `address.*` | GSTIN_STATE, PINCODE, REQ_FIELDS |
| `bank.*` | IFSC, ACCOUNT_NO, ACCOUNT_NAME, CHEQUE_MATCH |
| `contact.*` | EMAIL, PHONE, REQ_FIELDS |
| `legal_name`, `entity_type`, `proprietor_name` | PAN_TYPE, ACCOUNT_NAME, GST_DOC_MATCH, REQ_FIELDS |
| anything else | REQ_FIELDS |

---

## 6. Decision logic

See Data Schema §4. Restated:

```
risk = Σ weight[severity] for failed checks + 5 × (#warnings), capped at 100
       weights: warn 5 · blocker 12 · review 35 · reject 45

if any fail severity == reject  → REJECTED · "Closed: rejected"    · headline = first reject detail
elif any fail severity == review → PENDING  · "Compliance review"  · headline = first review detail
elif any fail severity == blocker→ PENDING  · "Awaiting vendor"    · headline = "{n} item(s) the vendor needs to fix"
elif risk >= 30                  → PENDING  · "Procurement review" · headline = "No hard failures but {n} risk signals stack up"
else                             → APPROVED · "Ready for vendor master" · headline = "All identity, bank, document and fraud checks passed" (+ " ({n} minor note(s))" if warnings)

risk_level: <20 Low · 20–49 Medium · ≥50 High
```

**Why this order:** the most severe signal must win. A fraud signal mixed with typos is still a fraud case; asking the fraudster to fix typos would be absurd.

---

## 7. Vendor email templates

`asks` = vendor_ask of every failed check with a non-empty ask, in pipeline order.

| Status / queue | Subject | Body (essence; exact text in `engine/messages.py`) |
|---|---|---|
| APPROVED | `Vendor onboarding approved: {company} [{ref}]` | Approved, bank verified, quote ref on invoices |
| PENDING · Awaiting vendor | `Action needed: {n} item(s) to complete your vendor registration [{ref}]` | "We're almost there…" + numbered asks + "You only need to update these items; everything else has been verified. Just resubmit with reference {ref}." |
| PENDING · Compliance review / Procurement review | `Your vendor registration is under review [{ref}]` | Neutral: with the team for a final verification step; we may call you on the number **originally registered**; no action needed. **No asks, no reasons.** |
| REJECTED | `Update on your vendor registration [{ref}]` | Thank you; can't proceed; bullet list of asks (only the non-empty, safe ones); if none: "We were unable to verify the details provided." + reply if you believe this is a mistake |

Sign-off: "Thanks,\nProcurement Team". Greeting: "Hi {contact.name},".

**Optional LLM polish (same OpenRouter model):** rewrites email tone only and remains an unapproved suggestion. Preserve every exact request and identifier; add no requests or promises. If a request or identifier is changed, the suggestion is discarded and the deterministic template remains the message of record.

---

## 8. Name normalisation & similarity

```
lowercase
"A.B.C." → "abc"                      (dotted initials collapsed)
"m/s" removed · "&" → " and " · "private"→"pvt" · "limited"→"ltd"
"company"→"co" · "corporation"→"corp" · "the" removed
non-alphanumerics → space
"a b c" → "abc"                       (spaced single letters collapsed)
collapse whitespace, trim
similarity = rapidfuzz.fuzz.token_sort_ratio(norm(a), norm(b))   # 0–100, word-order insensitive
```

## 9. GSTIN checksum algorithm

```
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
total = 0
for i, ch in enumerate(gstin[:14]):
    prod = CHARS.index(ch) * (1 if i % 2 == 0 else 2)
    total += prod // 36 + prod % 36
check = CHARS[(36 - total % 36) % 36]      # must equal gstin[14]
```
Verified identical to `python-stdnum`'s `stdnum.in_.gstin.is_valid` on all sample GSTINs (this is a unit test).

---

## 10. Check → stage order (as displayed)

1. intake: REQ_FIELDS, EMAIL, PHONE, PINCODE
2. identity: PAN_FORMAT, PAN_TYPE, PAN_INITIAL, GSTIN_VALID, GSTIN_PAN_LINK, GSTIN_STATE
3. bank: IFSC, IFSC_BANK, ACCOUNT_NO, ACCOUNT_NAME
4. documents: DOC_UNKNOWN*, DOC_AI_REVIEW (optional), DOC_ANALYST_REVIEW (after confirmation), DOC_DUPLICATE_FILE (when identical content is uploaded more than once), DOC_GST_CERTIFICATE, DOC_PAN_CARD, DOC_CANCELLED_CHEQUE, GST_DOC_MATCH, PAN_DOC_MATCH, CHEQUE_MATCH
5. fraud: DUP_VENDOR, DUP_BANK, DUP_NAME_REVIEW, RESUB_DIFF, RESUB_BANK_CHANGE, RESUB_CONTACT_CHANGE

Total: 27 core checks. Conditional findings include DOC_AI_REVIEW, DOC_DUPLICATE_FILE, and DOC_ANALYST_REVIEW.

`DOC_DUPLICATE_FILE` compares SHA-256 hashes of uploaded bytes, so a byte-identical PDF remains detectable after a filename change. It is a warning and includes internal filenames only.

`DUP_NAME_REVIEW` compares normalized legal names with the vendor master. A similarity of at least 90% for sufficiently distinctive names routes the submission to Compliance review. It is never a rejection by itself and does not expose another vendor's record to the submitter.

An analyst can confirm or correct uncertain document candidates only after checking the original PDF. The system reruns deterministic checks using accepted values, preserves the AI output, and appends a reviewer, timestamp, reason, original/accepted values, and resulting decision to a separate review-event table. A review event does not increment the vendor submission version. In this single-user demo the reviewer name is self-reported, not authenticated.
