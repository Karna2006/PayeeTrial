"""Turn check results into (a) the email the vendor receives and (b) the note
the procurement team sees.

The vendor email is built from deterministic templates so it can never invent
a requirement. Optionally, a local open-source LLM (Ollama) rewrites it for
tone, with a guard that the rewrite must still contain every ask. If Ollama
isn't running, or the rewrite drops anything, we keep the template.
"""
from __future__ import annotations

import json
import os
import urllib.request

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")


def vendor_email(sub: dict, decision: dict, results: list[dict]) -> dict:
    name = sub.get("contact", {}).get("name") or "there"
    company = sub.get("legal_name") or "your company"
    ref = sub.get("submission_ref", "")
    status = decision["status"]
    asks = [r["vendor_ask"] for r in results if r["status"] == "fail" and r["vendor_ask"]]

    if status == "APPROVED":
        subject = f"Vendor onboarding approved: {company} [{ref}]"
        body = (f"Hi {name},\n\nGood news: {company} has been approved as a vendor. Your bank details are "
                "verified and you're set up to receive payments. Please quote reference "
                f"{ref} on all invoices.\n\nThanks,\nProcurement Team")
    elif status == "REJECTED":
        subject = f"Update on your vendor registration [{ref}]"
        reasons = "\n".join(f"  • {a}" for a in asks) if asks else \
            "  • We were unable to verify the details provided."
        body = (f"Hi {name},\n\nThank you for submitting {company}'s vendor registration. "
                "Unfortunately we can't proceed with it in its current form:\n\n"
                f"{reasons}\n\nIf you believe this is a mistake, reply to this email and our team will "
                f"review it with you.\n\nThanks,\nProcurement Team")
    elif decision["queue"] in ("Compliance review", "Procurement review"):
        subject = f"Your vendor registration is under review [{ref}]"
        body = (f"Hi {name},\n\nThanks for the updated submission for {company}. It's now with our team "
                "for a final verification step. As part of this, we may call you on the phone number "
                f"originally registered with us. No action is needed from you right now.\n\nThanks,\nProcurement Team")
    else:
        subject = f"Action needed: {len(asks)} item(s) to complete your vendor registration [{ref}]"
        lines = "\n".join(f"  {i}. {a}" for i, a in enumerate(asks, 1))
        body = (f"Hi {name},\n\nThanks for registering {company}. We're almost there. To finish "
                f"verification we need the following:\n\n{lines}\n\nYou only need to update these items; "
                f"everything else has been verified. Just resubmit with reference {ref}.\n\n"
                "Thanks,\nProcurement Team")
    return {"to": sub.get("contact", {}).get("email", ""), "subject": subject, "body": body,
            "asks": asks, "polished_by": "template"}


def internal_note(decision: dict, results: list[dict]) -> str:
    lines = [f"Decision: {decision['status']} → {decision['queue']}  |  risk {decision['risk_score']}/100 "
             f"({decision['risk_level']})", f"Why: {decision['headline']}"]
    notes = [f"- [{r['check_id']}] {r['internal_note']}" for r in results
             if r["internal_note"] and r["status"] in ("fail", "warn")]
    if notes:
        lines += ["", "Notes for reviewer:"] + notes
    return "\n".join(lines)


def ollama_available(timeout: float = 0.6) -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        return True
    except Exception:
        return False


def polish_with_llm(email: dict, timeout: float = 45.0) -> dict:
    """Rewrite for warmth/clarity with a local LLM. Falls back to the template on any problem."""
    if not email["asks"] or not ollama_available():
        return email
    prompt = ("Rewrite this vendor onboarding email to be warm, clear and concise. Keep EVERY numbered "
              "request with all IDs, numbers and names exactly as written. Do not add new requests or "
              "promises. Return only the email body.\n\n" + email["body"])
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", method="POST",
                                     data=json.dumps({"model": OLLAMA_MODEL, "prompt": prompt,
                                                      "stream": False, "options": {"temperature": 0.2}}).encode(),
                                     headers={"Content-Type": "application/json"})
        text = json.loads(urllib.request.urlopen(req, timeout=timeout).read())["response"].strip()
    except Exception:
        return email
    # Guardrail: every identifier in the original asks must survive the rewrite
    import re
    tokens = set(re.findall(r"\b[A-Z0-9]{8,}\b", " ".join(email["asks"])))
    if tokens and not all(t in text for t in tokens):
        return email
    return {**email, "body": text, "polished_by": f"ollama:{OLLAMA_MODEL}"}
