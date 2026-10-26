"""Gate 0: is this a money or data ask? (Nemotron Nano)"""
from pydantic import BaseModel

from app.clients.llm import complete_json
from app.config import load_settings
from app.phase_a.models import Email, Intent

SYSTEM = (
    "You classify business emails for an accounts-payable clerk. "
    "Return only JSON: {\"intent\": one of \"bank_change\", \"payment_request\", \"gift_cards\", "
    "\"payroll_change\", \"data_request\", \"none\"}. "
    "bank_change: new or changed bank/remittance details. payroll_change: change to an employee's direct deposit. "
    "data_request: asks for employee, tax, or customer records. none: no money or data is requested."
)


class IntentOut(BaseModel):
    intent: Intent


async def classify_intent(e: Email) -> Intent:
    attachments = ", ".join(a.filename for a in e.attachments) or "none"
    user = f"Subject: {e.subject}\nAttachments: {attachments}\n\n{e.body_text[:4000]}"
    out = await complete_json(
        step="gate0", key=e.message_id, model=load_settings().model_nano,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        schema=IntentOut,
    )
    return out.intent
