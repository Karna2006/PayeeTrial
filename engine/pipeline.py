"""The onboarding pipeline.

Five verification stages run in order, then a decision stage. Each check
returns a CheckResult with: what was checked, what we saw (evidence), how bad
a failure is (severity), what to ask the vendor, and an internal note.

Severity on failure decides the outcome:
    warn     -> noted, does not block approval
    blocker  -> vendor can fix it        -> PENDING (awaiting vendor)
    review   -> needs a human            -> PENDING (internal review)
    reject   -> hard stop                -> REJECTED
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterator

import pandas as pd

from . import validators as V
from .documents import ParsedDoc

PASS, FAIL, WARN, INFO = "pass", "fail", "warn", "info"
SEVERITY_WEIGHT = {"warn": 5, "blocker": 12, "review": 35, "reject": 45}

STAGES = [
    ("intake", "Intake & completeness"),
    ("identity", "Identity: PAN + GSTIN"),
    ("bank", "Bank details"),
    ("documents", "Document cross-check"),
    ("fraud", "Duplicate & fraud screening"),
]

REQUIRED_FIELDS = [
    ("legal_name", "Registered legal name"), ("entity_type", "Entity type"), ("pan", "PAN"),
    ("gstin", "GSTIN"), ("address.line1", "Registered address"), ("address.city", "City"),
    ("address.state", "State"), ("address.pincode", "PIN code"), ("contact.name", "Contact person"),
    ("contact.email", "Contact email"), ("contact.phone", "Contact phone"),
    ("bank.account_holder", "Bank account holder name"), ("bank.account_number", "Bank account number"),
    ("bank.ifsc", "IFSC code"), ("bank.bank_name", "Bank name"),
]
REQUIRED_DOCS = ["gst_certificate", "pan_card", "cancelled_cheque"]
DOC_LABEL = {"gst_certificate": "GST registration certificate", "pan_card": "PAN card",
             "cancelled_cheque": "cancelled cheque"}


@dataclass
class CheckResult:
    check_id: str
    stage: str
    name: str
    status: str                 # pass / fail / warn / info
    detail: str                 # human-readable explanation
    severity: str = "blocker"   # applies when status == fail/warn
    evidence: dict = field(default_factory=dict)
    vendor_ask: str = ""        # what we tell the vendor to do
    internal_note: str = ""     # what we tell the procurement team
    tags: list = field(default_factory=list)


def get(d: dict, path: str, default=""):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part, default)
    return cur if cur is not None else default


def normalise_submission(sub: dict) -> dict:
    s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in sub.items()}
    s["pan"] = V.clean_id(s.get("pan"))
    s["gstin"] = V.clean_id(s.get("gstin"))
    bank = s.setdefault("bank", {})
    bank["ifsc"] = V.clean_id(bank.get("ifsc"))
    bank["account_number"] = V.clean_id(bank.get("account_number"))
    return s


# ==========================================================================
# Stage 1: intake
# ==========================================================================
def stage_intake(s: dict, ctx: dict) -> list[CheckResult]:
    out = []
    missing = [label for path, label in REQUIRED_FIELDS if not str(get(s, path)).strip()]
    if s.get("entity_type") == "Proprietorship" and not s.get("proprietor_name"):
        missing.append("Proprietor's full name")
    if missing:
        out.append(CheckResult("REQ_FIELDS", "intake", "Required fields present", FAIL,
                               f"{len(missing)} required field(s) missing: {', '.join(missing)}",
                               "blocker", {"missing": missing},
                               vendor_ask=f"Please fill in: {', '.join(missing)}."))
    else:
        out.append(CheckResult("REQ_FIELDS", "intake", "Required fields present", PASS,
                               f"All {len(REQUIRED_FIELDS)} required fields provided"))

    email = get(s, "contact.email")
    dom = V.domain_of(email)
    if email and "@" not in email:
        out.append(CheckResult("EMAIL", "intake", "Contact email", FAIL, f"'{email}' is not a valid email",
                               "blocker", vendor_ask="Please share a valid contact email address."))
    elif dom in V.FREE_EMAIL_DOMAINS and s.get("entity_type") != "Proprietorship":
        out.append(CheckResult("EMAIL", "intake", "Contact email", WARN,
                               f"Registered company using a free email domain ({dom})", "warn",
                               {"domain": dom}, internal_note="Free-mail domain on a company submission. "
                               "Weak signal on its own; weigh with other checks.", tags=["risk-signal"]))
    elif s.get("website") and dom and V.domain_of(s["website"]) != dom:
        out.append(CheckResult("EMAIL", "intake", "Contact email", WARN,
                               f"Email domain ({dom}) differs from website ({V.domain_of(s['website'])})",
                               "warn", internal_note="Domain mismatch, often benign (group email domains)."))
    else:
        out.append(CheckResult("EMAIL", "intake", "Contact email", PASS, f"Business domain {dom or '-'}"))

    phone = V.clean_phone(get(s, "contact.phone"))
    if phone and not (len(phone) == 10 and phone[0] in "6789"):
        out.append(CheckResult("PHONE", "intake", "Contact phone", FAIL, f"'{get(s, 'contact.phone')}' "
                               "is not a valid Indian mobile number", "blocker",
                               vendor_ask="Please share a valid 10-digit mobile number for verification calls."))
    elif phone:
        out.append(CheckResult("PHONE", "intake", "Contact phone", PASS, "Valid 10-digit mobile"))

    pin = str(get(s, "address.pincode"))
    if pin and not (pin.isdigit() and len(pin) == 6 and pin[0] != "0"):
        out.append(CheckResult("PINCODE", "intake", "PIN code", FAIL, f"'{pin}' is not a valid PIN code",
                               "blocker", vendor_ask="Please correct the PIN code of your registered address."))
    return out


# ==========================================================================
# Stage 2: identity
# ==========================================================================
def stage_identity(s: dict, ctx: dict) -> list[CheckResult]:
    out = []
    pan, gstin, etype = s["pan"], s["gstin"], s.get("entity_type", "")

    pan_ok = V.pan_valid(pan)
    if not pan_ok:
        out.append(CheckResult("PAN_FORMAT", "identity", "PAN format", FAIL,
                               f"'{pan}' does not match the PAN pattern AAAAA9999A", "blocker",
                               vendor_ask="Your PAN appears malformed. Please re-enter it exactly as on the PAN card."))
    else:
        out.append(CheckResult("PAN_FORMAT", "identity", "PAN format", PASS, f"{pan} is well-formed"))
        holder = pan[3]
        expected = V.ENTITY_EXPECTED_PAN_TYPE.get(etype)
        if expected and holder != expected:
            out.append(CheckResult(
                "PAN_TYPE", "identity", "PAN holder type matches entity type", FAIL,
                f"Declared '{etype}' but PAN's 4th character '{holder}' = "
                f"{V.PAN_HOLDER_TYPES.get(holder, 'unknown')} (expected '{expected}')", "blocker",
                {"pan_type": holder, "expected": expected},
                vendor_ask=f"The PAN you provided belongs to a {V.PAN_HOLDER_TYPES.get(holder, 'different holder type').lower()}, "
                           f"but you registered as a {etype}. Please provide the PAN of the business entity."))
        elif expected:
            out.append(CheckResult("PAN_TYPE", "identity", "PAN holder type matches entity type", PASS,
                                   f"'{holder}' = {V.PAN_HOLDER_TYPES[holder]}, consistent with {etype}"))
        # 5th char: first letter of the entity name (or surname for individuals)
        ref = (s.get("proprietor_name", "").split() or [""])[-1] if holder == "P" else V.strip_suffix(s.get("legal_name", ""))
        if ref and pan[4] != ref[0].upper():
            out.append(CheckResult("PAN_INITIAL", "identity", "PAN name initial", WARN,
                                   f"PAN 5th character '{pan[4]}' doesn't match the name initial '{ref[0].upper()}'",
                                   "warn", internal_note="Soft signal: PAN may belong to another entity. Covered by "
                                   "GSTIN link + PAN card checks."))

    if not V.gstin_format_valid(gstin):
        out.append(CheckResult("GSTIN_VALID", "identity", "GSTIN format + checksum", FAIL,
                               f"'{gstin}' is not a valid 15-character GSTIN", "blocker",
                               vendor_ask="Your GSTIN appears malformed. Please re-enter it exactly as on your GST certificate."))
        return out
    if not V.gstin_checksum_valid(gstin):
        out.append(CheckResult("GSTIN_VALID", "identity", "GSTIN format + checksum", FAIL,
                               f"Checksum digit wrong: expected '{V.gstin_checksum_char(gstin[:14])}', got '{gstin[14]}'",
                               "blocker", vendor_ask="Your GSTIN fails the checksum, which usually means a typo. "
                                                     "Please re-check it against your GST certificate."))
        return out
    out.append(CheckResult("GSTIN_VALID", "identity", "GSTIN format + checksum", PASS, f"{gstin} checksum OK"))

    # GSTIN carries the PAN in chars 3-12: the single strongest cross-field check
    emb = V.gstin_embedded_pan(gstin)
    if pan_ok:
        dist = V.hamming(emb, pan)
        card_pan = ctx.get("doc_fields", {}).get("pan_card", {}).get("pan")
        if dist == 0:
            out.append(CheckResult("GSTIN_PAN_LINK", "identity", "PAN embedded in GSTIN", PASS,
                                   f"GSTIN chars 3-12 = {emb} = submitted PAN"))
        elif dist == 1:
            hint = (f" Your PAN card shows {card_pan}, matching the GSTIN, so the form entry looks like a typo."
                    if card_pan == emb else "")
            out.append(CheckResult(
                "GSTIN_PAN_LINK", "identity", "PAN embedded in GSTIN", FAIL,
                f"GSTIN embeds {emb}, form says {pan}: one character apart (likely typo)", "blocker",
                {"gstin_pan": emb, "form_pan": pan, "pan_card": card_pan},
                vendor_ask=f"Your PAN ({pan}) and the PAN inside your GSTIN ({emb}) differ by one character.{hint} "
                           "Please confirm the correct PAN."))
        else:
            out.append(CheckResult(
                "GSTIN_PAN_LINK", "identity", "PAN embedded in GSTIN", FAIL,
                f"GSTIN belongs to PAN {emb}, a different legal entity from submitted PAN {pan}", "reject",
                {"gstin_pan": emb, "form_pan": pan},
                vendor_ask="The GST registration you provided belongs to a different legal entity than your PAN. "
                           "We can only onboard a vendor whose GSTIN and PAN belong to the same entity.",
                internal_note="Identity mismatch: GSTIN and PAN belong to different entities. Possible borrowed GSTIN.",
                tags=["fraud-signal"]))

    gst_state = V.gstin_state(gstin)
    addr_state = get(s, "address.state")
    if gst_state and addr_state and gst_state.lower() != addr_state.lower():
        out.append(CheckResult(
            "GSTIN_STATE", "identity", "GSTIN state matches address", FAIL,
            f"GSTIN state code {gstin[:2]} = {gst_state}, but registered address is in {addr_state}", "blocker",
            {"gstin_state": gst_state, "address_state": addr_state},
            vendor_ask=f"Your GSTIN is registered in {gst_state} (state code {gstin[:2]}), but your address is in "
                       f"{addr_state}. GST is state-specific: please share the GSTIN for your {addr_state} "
                       f"registration (it should start with {V.STATE_TO_CODE.get(addr_state.lower(), '??')}), "
                       f"or update the address if you'll invoice from {gst_state}."))
    elif gst_state:
        out.append(CheckResult("GSTIN_STATE", "identity", "GSTIN state matches address", PASS,
                               f"State code {gstin[:2]} = {gst_state}"))
    return out


# ==========================================================================
# Stage 3: bank
# ==========================================================================
def stage_bank(s: dict, ctx: dict) -> list[CheckResult]:
    out = []
    b = s.get("bank", {})
    ifsc, acc = b.get("ifsc", ""), b.get("account_number", "")
    if not V.ifsc_valid(ifsc):
        out.append(CheckResult("IFSC", "bank", "IFSC format", FAIL, f"'{ifsc}' is not a valid IFSC (AAAA0XXXXXX)",
                               "blocker", vendor_ask="Your IFSC code looks incorrect. Please check it on your cheque."))
    else:
        bank = V.ifsc_bank(ifsc)
        out.append(CheckResult("IFSC", "bank", "IFSC format", PASS,
                               f"{ifsc} is well-formed ({bank or 'bank code ' + ifsc[:4]})"))
        stated = b.get("bank_name", "")
        if bank and stated and V.name_similarity(bank, stated) < 70:
            out.append(CheckResult("IFSC_BANK", "bank", "IFSC matches stated bank", WARN,
                                   f"IFSC prefix {ifsc[:4]} = {bank}, but form says '{stated}'", "warn",
                                   {"ifsc_bank": bank, "stated": stated},
                                   internal_note="Bank name and IFSC disagree. Data-entry slip or details pasted "
                                                 "from someone else's account.", tags=["risk-signal"]))
    if not V.account_number_valid(acc):
        out.append(CheckResult("ACCOUNT_NO", "bank", "Account number format", FAIL,
                               f"'{acc}' should be 9-18 digits", "blocker",
                               vendor_ask="Your bank account number looks incorrect. Please re-check it."))

    holder = b.get("account_holder", "")
    legal = s.get("legal_name", "")
    sim = V.name_similarity(holder, legal)
    if not holder:
        return out
    # Proprietor match is tested first so the run view explains *why* a personal account is acceptable.
    if s.get("entity_type") == "Proprietorship" and s.get("proprietor_name") and \
            V.name_similarity(holder, s["proprietor_name"]) >= 88:
        out.append(CheckResult("ACCOUNT_NAME", "bank", "Account holder = legal entity", PASS,
                               f"Account is in proprietor's name '{holder}'. Valid for a proprietorship, "
                               "since the proprietor and the business are the same legal person.",
                               evidence={"similarity_to_proprietor": V.name_similarity(holder, s['proprietor_name'])}))
    elif sim >= 88:
        out.append(CheckResult("ACCOUNT_NAME", "bank", "Account holder = legal entity", PASS,
                               f"'{holder}' ≈ '{legal}' (similarity {sim})", evidence={"similarity": sim}))
    elif sim >= 70:
        out.append(CheckResult("ACCOUNT_NAME", "bank", "Account holder = legal entity", FAIL,
                               f"'{holder}' is close to but not the same as '{legal}' (similarity {sim})", "blocker",
                               {"similarity": sim},
                               vendor_ask=f"The bank account name ('{holder}') doesn't exactly match your registered "
                                          f"name ('{legal}'). Please confirm the account belongs to your business, "
                                          "or share a cancelled cheque showing the registered name."))
    else:
        out.append(CheckResult("ACCOUNT_NAME", "bank", "Account holder = legal entity", FAIL,
                               f"Account held by '{holder}', an unrelated party to '{legal}' (similarity {sim})",
                               "reject", {"similarity": sim},
                               vendor_ask="We can only make payments to a bank account held in your registered "
                                          "business name. Third-party accounts can't be accepted.",
                               internal_note="Third-party bank account. The #1 vendor payment-fraud pattern.",
                               tags=["fraud-signal"]))
    return out


# ==========================================================================
# Stage 4: documents
# ==========================================================================
def stage_documents(s: dict, ctx: dict) -> list[CheckResult]:
    out = []
    docs: list[ParsedDoc] = ctx.get("docs", [])
    by_type = {}
    for d in docs:
        by_type.setdefault(d.doc_type, d)
    for d in docs:
        if d.doc_type == "unknown":
            out.append(CheckResult("DOC_UNKNOWN", "documents", f"Recognise '{d.filename}'", WARN,
                                   f"Couldn't recognise '{d.filename}' as any expected document", "warn"))
        if d.ai_review and d.ai_review.get("needs_review") and not d.analyst_review:
            reason = d.ai_review.get("review_reason") or "Document values came from visual-only AI extraction."
            out.append(CheckResult("DOC_AI_REVIEW", "documents", f"Review AI extraction for '{d.filename}'", FAIL,
                                   reason, "review", {"filename": d.filename,
                                   "model": d.ai_review.get("model", "AI")},
                                   internal_note="Confirm document type and extracted values against the original PDF "
                                                 "before approving. AI document scoring is advisory."))
        if d.analyst_review:
            audit = d.analyst_review
            out.append(CheckResult("DOC_ANALYST_REVIEW", "documents", f"Analyst confirmed '{d.filename}'", INFO,
                                   f"{audit.get('action', 'reviewed').capitalize()} by {audit.get('reviewer', 'analyst')}: "
                                   f"{audit.get('reason', '')}", "info",
                                   {"filename": d.filename, "reviewed_at": audit.get("created_at"),
                                    "document_type": d.doc_type},
                                   internal_note="Accepted fields were checked against the original uploaded PDF."))

    hashes: dict[str, list[str]] = {}
    for d in docs:
        if d.sha256:
            hashes.setdefault(d.sha256, []).append(d.filename)
    repeated = [names for names in hashes.values() if len(names) > 1]
    if repeated:
        labels = [", ".join(names) for names in repeated]
        out.append(CheckResult("DOC_DUPLICATE_FILE", "documents", "No duplicate document contents", WARN,
                               "Identical PDF content was uploaded more than once: " + "; ".join(labels), "warn",
                               {"duplicate_filenames": [name for names in repeated for name in names]},
                               internal_note="SHA-256 content match; filenames may differ. Review whether each upload is needed."))
    dup_types = [t for t in REQUIRED_DOCS if sum(1 for d in docs if d.doc_type == t) > 1]

    for t in REQUIRED_DOCS:
        if t not in by_type:
            extra = ""
            if dup_types:
                extra = f" We received {DOC_LABEL[dup_types[0]]} twice; one of the uploads may have been the wrong file."
            out.append(CheckResult(f"DOC_{t.upper()}", "documents", f"{DOC_LABEL[t].capitalize()} provided", FAIL,
                                   f"No {DOC_LABEL[t]} found among uploads ({', '.join(d.label for d in docs) or 'none'})",
                                   "blocker", vendor_ask=f"Please upload your {DOC_LABEL[t]}.{extra}"))
        else:
            out.append(CheckResult(f"DOC_{t.upper()}", "documents", f"{DOC_LABEL[t].capitalize()} provided", PASS,
                                   f"Found in '{by_type[t].filename}'"))

    gst = by_type.get("gst_certificate")
    if gst:
        f = gst.fields
        problems = []
        if f.get("gstin") and f["gstin"] != s["gstin"]:
            problems.append(f"certificate GSTIN {f['gstin']} ≠ form GSTIN {s['gstin']}")
        if f.get("legal_name"):
            sim = V.name_similarity(f["legal_name"], s.get("legal_name", ""))
            if sim < 90:
                problems.append(f"certificate is for '{f['legal_name']}', not '{s.get('legal_name')}' (similarity {sim})")
        if (f.get("status") or "").lower() in {"cancelled", "suspended", "inactive"}:
            problems.append(f"registration status is {f['status']}")
        if problems:
            out.append(CheckResult("GST_DOC_MATCH", "documents", "GST certificate matches form", FAIL,
                                   "; ".join(problems), "blocker", f,
                                   vendor_ask="The GST certificate you uploaded doesn't match your submission ("
                                              + "; ".join(problems) + "). Please upload the certificate for "
                                              f"{s.get('legal_name')} with GSTIN {s['gstin']}."))
        else:
            out.append(CheckResult("GST_DOC_MATCH", "documents", "GST certificate matches form", PASS,
                                   f"GSTIN + legal name on certificate match ({f.get('status', 'status n/a')})", evidence=f))

    pan_doc = by_type.get("pan_card")
    if pan_doc and pan_doc.fields.get("pan"):
        card = pan_doc.fields["pan"]
        if card != s["pan"]:
            emb = V.gstin_embedded_pan(s["gstin"]) if V.gstin_format_valid(s["gstin"]) else ""
            note = " It matches the PAN inside your GSTIN, so the form entry is likely a typo." if card == emb else ""
            out.append(CheckResult("PAN_DOC_MATCH", "documents", "PAN card matches form", FAIL,
                                   f"PAN card shows {card}, form says {s['pan']}", "blocker", pan_doc.fields,
                                   vendor_ask=f"Your PAN card shows {card} but the form says {s['pan']}.{note} "
                                              "Please correct the PAN on the form."))
        else:
            out.append(CheckResult("PAN_DOC_MATCH", "documents", "PAN card matches form", PASS, f"PAN card shows {card}"))

    chq = by_type.get("cancelled_cheque")
    if chq:
        f, b = chq.fields, s.get("bank", {})
        problems = []
        if f.get("account_number") and f["account_number"] != b.get("account_number"):
            problems.append(f"cheque A/C {f['account_number']} ≠ form A/C {b.get('account_number')}")
        if f.get("ifsc") and f["ifsc"] != b.get("ifsc"):
            problems.append(f"cheque IFSC {f['ifsc']} ≠ form IFSC {b.get('ifsc')}")
        if problems:
            out.append(CheckResult("CHEQUE_MATCH", "documents", "Cancelled cheque matches bank details", FAIL,
                                   "; ".join(problems), "blocker", f,
                                   vendor_ask="Your cancelled cheque doesn't match the bank details on the form ("
                                              + "; ".join(problems) + "). Please correct one of them."))
        else:
            out.append(CheckResult("CHEQUE_MATCH", "documents", "Cancelled cheque matches bank details", PASS,
                                   f"A/C + IFSC on cheque match form", evidence=f))
    return out


# ==========================================================================
# Stage 5: duplicates, fraud, resubmission behaviour
# ==========================================================================
def stage_fraud(s: dict, ctx: dict) -> list[CheckResult]:
    out = []
    master: pd.DataFrame = ctx.get("master", pd.DataFrame())
    if not master.empty:
        same_pan = master[master["pan"] == s["pan"]]
        if not same_pan.empty:
            r = same_pan.iloc[0]
            out.append(CheckResult("DUP_VENDOR", "fraud", "Not already an existing vendor", FAIL,
                                   f"PAN {s['pan']} already onboarded as {r['vendor_id']} ({r['legal_name']})", "reject",
                                   {"vendor_id": r["vendor_id"]},
                                   vendor_ask="You're already registered with us as a vendor. If your details have "
                                              "changed, please use the vendor-update process instead.",
                                   internal_note=f"Duplicate of {r['vendor_id']}. Route to change-request, not new onboarding."))
        else:
            out.append(CheckResult("DUP_VENDOR", "fraud", "Not already an existing vendor", PASS,
                                   f"PAN not found among {len(master)} existing vendors"))

        acc = s.get("bank", {}).get("account_number")
        same_acc = master[(master["bank_account"].astype(str) == str(acc)) & (master["pan"] != s["pan"])]
        if not same_acc.empty:
            r = same_acc.iloc[0]
            out.append(CheckResult("DUP_BANK", "fraud", "Bank account not used by another vendor", FAIL,
                                   f"Account {acc} already belongs to vendor {r['vendor_id']} ({r['legal_name']})",
                                   "reject", {"vendor_id": r["vendor_id"], "vendor": r["legal_name"]},
                                   vendor_ask="",
                                   internal_note=f"Bank account shared with existing vendor {r['vendor_id']} "
                                                 f"({r['legal_name']}). Do NOT disclose this to the submitter. "
                                                 "Investigate for collusion / shell vendor.",
                                   tags=["fraud-signal"]))
        else:
            out.append(CheckResult("DUP_BANK", "fraud", "Bank account not used by another vendor", PASS,
                                   "Account number is unique in vendor master"))

        # Similar legal names are only a triage signal. Exact PAN matching above
        # remains its own rule, and fuzzy matches never reject by themselves.
        submitted_name = V.normalize_name(s.get("legal_name", ""))
        if len(submitted_name) >= 12 and len(submitted_name.split()) >= 2:
            candidates = master[master["pan"] != s.get("pan", "")]
            matches = []
            for _, row in candidates.iterrows():
                existing_name = str(row.get("legal_name", ""))
                existing_norm = V.normalize_name(existing_name)
                if len(existing_norm) < 12 or len(existing_norm.split()) < 2:
                    continue
                similarity = V.name_similarity(s.get("legal_name", ""), existing_name)
                if similarity >= 90:
                    matches.append((similarity, str(row.get("vendor_id", "")), existing_name))
            if matches:
                matches.sort(reverse=True)
                best = matches[0]
                out.append(CheckResult("DUP_NAME_REVIEW", "fraud", "Review similar vendor legal names", FAIL,
                                       f"Legal name is {best[0]}% similar to existing vendor {best[1]} ({best[2]}).",
                                       "review", {"similarity": best[0], "vendor_id": best[1]}, vendor_ask="",
                                       internal_note="Possible related or duplicate entity; compare registration identifiers. "
                                                     "Name similarity is not proof of identity and must not cause rejection."))
            else:
                out.append(CheckResult("DUP_NAME_REVIEW", "fraud", "No near-duplicate legal name found", PASS,
                                       "No sufficiently similar legal name found in the vendor master."))

    prev = ctx.get("previous")
    if prev:
        before, after = prev["submission"], s
        changed = diff_submissions(before, after)
        ctx["diff"] = changed
        out.append(CheckResult("RESUB_DIFF", "fraud", f"Resubmission v{prev['version'] + 1} vs v{prev['version']}",
                               INFO, f"Changed: {', '.join(changed) or 'nothing'}", "info",
                               evidence={"changed": changed}))
        bank_changed = [c for c in changed if c.startswith("bank.account_number") or c.startswith("bank.ifsc")]
        asked_bank = any(r["stage"] == "bank" or r["check_id"] == "CHEQUE_MATCH"
                         for r in prev["results"] if r["status"] == FAIL)
        if bank_changed and not asked_bank:
            old_phone = get(before, "contact.phone")
            out.append(CheckResult(
                "RESUB_BANK_CHANGE", "fraud", "Bank details stable across resubmission", FAIL,
                f"Bank account changed ({get(before, 'bank.account_number')} → {get(after, 'bank.account_number')}) "
                "although the previous review never asked for bank changes", "review",
                {"old_account": get(before, "bank.account_number"), "new_account": get(after, "bank.account_number")},
                vendor_ask="",
                internal_note="Unrequested bank change mid-onboarding: classic account-takeover / BEC pattern. "
                              f"Hold. Verify by calling back on the ORIGINAL number on file ({old_phone}), "
                              "never on contact details from the new submission.",
                tags=["fraud-signal"]))
        elif bank_changed:
            out.append(CheckResult("RESUB_BANK_CHANGE", "fraud", "Bank details stable across resubmission", PASS,
                                   "Bank details changed in response to an earlier request"))
        if "contact.phone" in changed and "contact.email" in changed:
            out.append(CheckResult("RESUB_CONTACT_CHANGE", "fraud", "Contact details stable", WARN,
                                   "Both phone and email changed on resubmission", "warn",
                                   internal_note="Both contact channels swapped. Verify through original channel.",
                                   tags=["risk-signal"]))
    return out


STAGE_FUNCS: dict[str, Callable] = {
    "intake": stage_intake, "identity": stage_identity, "bank": stage_bank,
    "documents": stage_documents, "fraud": stage_fraud,
}


def _flatten(d: dict, prefix="") -> dict:
    out = {}
    for k, v in d.items():
        if k in ("documents", "submission_ref"):
            continue
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def _comparable(key: str, value) -> str:
    """Phone formatting is not a change; compare the normalised number."""
    text = str(value if value is not None else "").strip()
    return V.clean_phone(text) if key == "contact.phone" else text


def diff_submissions(a: dict, b: dict) -> list[str]:
    fa, fb = _flatten(a), _flatten(b)
    return sorted(k for k in set(fa) | set(fb) if _comparable(k, fa.get(k, "")) != _comparable(k, fb.get(k, "")))


# Rules Spec §5: a changed field is "requested" if the previous version failed a check that maps to it.
REQUESTED_BY: dict[str, set[str]] = {
    "pan": {"PAN_FORMAT", "PAN_TYPE", "GSTIN_PAN_LINK", "PAN_DOC_MATCH"},
    "gstin": {"GSTIN_VALID", "GSTIN_PAN_LINK", "GSTIN_STATE", "GST_DOC_MATCH"},
    "address": {"GSTIN_STATE", "PINCODE", "REQ_FIELDS"},
    "bank": {"IFSC", "ACCOUNT_NO", "ACCOUNT_NAME", "CHEQUE_MATCH"},
    "contact": {"EMAIL", "PHONE", "REQ_FIELDS"},
    "legal_name": {"PAN_TYPE", "ACCOUNT_NAME", "GST_DOC_MATCH", "REQ_FIELDS"},
    "entity_type": {"PAN_TYPE", "ACCOUNT_NAME", "GST_DOC_MATCH", "REQ_FIELDS"},
    "proprietor_name": {"PAN_TYPE", "ACCOUNT_NAME", "GST_DOC_MATCH", "REQ_FIELDS"},
}
REQUESTED_DEFAULT = {"REQ_FIELDS"}


def classify_changes(prev_sub: dict, sub: dict, prev_results: list[dict]) -> list[dict]:
    """Field-level diff between two versions, each change marked requested / unrequested.

    Feeds the UI diff table: an unrequested change is what a reviewer should look at first.
    """
    before, after = normalise_submission(prev_sub), normalise_submission(sub)
    failed = {r["check_id"] for r in prev_results if r["status"] == FAIL}
    fa, fb = _flatten(before), _flatten(after)
    return [{"field": k, "before": str(fa.get(k, "")), "after": str(fb.get(k, "")),
             "requested": bool(failed & REQUESTED_BY.get(k.split(".")[0], REQUESTED_DEFAULT))}
            for k in diff_submissions(before, after)]


# ==========================================================================
# Decision
# ==========================================================================
def decide(results: list[CheckResult]) -> dict:
    fails = [r for r in results if r.status == FAIL]
    warns = [r for r in results if r.status == WARN]
    score = sum(SEVERITY_WEIGHT.get(r.severity, 0) for r in fails) + SEVERITY_WEIGHT["warn"] * len(warns)
    score = min(100, score)
    by = lambda sev: [r for r in fails if r.severity == sev]

    if by("reject"):
        status, queue = "REJECTED", "Closed: rejected"
        headline = by("reject")[0].detail
    elif by("review"):
        status, queue = "PENDING", "Compliance review"
        headline = by("review")[0].detail
    elif by("blocker"):
        status, queue = "PENDING", "Awaiting vendor"
        headline = f"{len(by('blocker'))} item(s) the vendor needs to fix"
    elif score >= 30:
        status, queue = "PENDING", "Procurement review"
        headline = f"No hard failures but {len(warns)} risk signals stack up"
    else:
        status, queue = "APPROVED", "Ready for vendor master"
        headline = "All identity, bank, document and fraud checks passed" + (
            f" ({len(warns)} minor note(s))" if warns else "")

    level = "Low" if score < 20 else "Medium" if score < 50 else "High"
    return {"status": status, "queue": queue, "headline": headline, "risk_score": score, "risk_level": level,
            "fraud_signals": [r.check_id for r in results if "fraud-signal" in r.tags and r.status == FAIL],
            "n_pass": sum(r.status == PASS for r in results), "n_fail": len(fails), "n_warn": len(warns)}


def run(sub: dict, docs: list[ParsedDoc], master: pd.DataFrame, previous: dict | None = None,
        delay: float = 0.0) -> Iterator[tuple[str, str, list[CheckResult], float]]:
    """Yields (stage_key, stage_label, results, elapsed_ms) as each stage finishes."""
    s = normalise_submission(sub)
    doc_fields: dict = {}
    for d in docs:  # first upload of each type wins, same as stage_documents
        doc_fields.setdefault(d.doc_type, d.fields)
    ctx = {"docs": docs, "master": master, "previous": previous, "doc_fields": doc_fields}
    for key, label in STAGES:
        t0 = time.perf_counter()
        results = STAGE_FUNCS[key](s, ctx)
        if delay:
            time.sleep(delay)
        yield key, label, results, (time.perf_counter() - t0) * 1000


def run_all(sub: dict, docs: list[ParsedDoc], master: pd.DataFrame, previous: dict | None = None) -> dict:
    results = []
    for key, _, res, _ in run(sub, docs, master, previous):
        results.extend(res)
    return {"results": [asdict(r) for r in results], "decision": decide(results)}
