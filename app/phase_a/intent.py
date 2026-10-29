"""Gate 0: is this a money or data ask? (Nemotron Nano, with a code backstop)"""
import re

from pydantic import BaseModel

from app.clients.llm import complete_json
from app.config import load_settings
from app.phase_a.content import extract_payment_details
from app.phase_a.models import Email, Intent

# Words that mean money or data may be involved. Broad on purpose: a false hit only costs one extra check.
_MONEY_RE = re.compile(r"\b(invoices?|wire|payments?|pay|remittance|bank|routing|account number|gift ?cards?|w-?2s?|"
                       r"direct deposit|payroll)\b", re.IGNORECASE)

SYSTEM = (
    "You classify business emails for an accounts-payable clerk. "
    "Return only JSON: {\"intent\": one of \"bank_change\", \"payment_request\", \"gift_cards\", "
    "\"payroll_change\", \"data_request\", \"none\", \"claimed_company\": the company the sender says they "
    "represent, or null if they write as an individual}. "
    "bank_change: new or changed bank/remittance details. payroll_change: change to an employee's direct deposit. "
    "data_request: asks for employee, tax, or customer records. none: no money or data is requested."
)


class IntentOut(BaseModel):
    intent: Intent
    claimed_company: str | None = None


async def classify_intent(e: Email) -> IntentOut:
    attachments = ", ".join(a.filename for a in e.attachments) or "none"
    user = f"From: {e.from_name}\nSubject: {e.subject}\nAttachments: {attachments}\n\n{e.body_text[:4000]}"
    return await complete_json(
        step="gate0", key=e.message_id, model=load_settings().model_nano,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        schema=IntentOut, default=IntentOut(intent=Intent.PAYMENT_REQUEST),  # safe: never skip the checks
    )


def needs_checks(e: Email) -> bool:
    """Code backstop for the gate: the email's text could talk Nano into "none", so bank details, a PDF or image
    (where Super VL could find bank details) or a money word keep the checks on whatever Nano says."""
    details = extract_payment_details(e.body_text)
    readable = any(a.content_type == "application/pdf" or a.content_type.startswith("image/") for a in e.attachments)
    return bool(details.account_last4 or details.routing_number or readable
                or _MONEY_RE.search(f"{e.subject}\n{e.body_text}"))
