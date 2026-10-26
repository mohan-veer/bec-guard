"""Content checks: payment details vs the ledger and request keywords (rules); language and writing style
(Nemotron Super); payment details from PDF/image attachments (Nemotron Super VL).
"""
import base64
import io
import re
from decimal import Decimal

import pypdfium2 as pdfium
from pydantic import BaseModel

from app.clients.llm import complete_json
from app.config import load_settings
from app.phase_a.models import Attachment, Email, PaymentDetails, Signal, Vendor, VendorLedger

_BANK_RE = re.compile(r"^\s*Bank(?: name)?:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_ROUTING_RE = re.compile(r"Routing(?: number)?:\s*(\d{9})", re.IGNORECASE)
_ACCOUNT_RE = re.compile(r"Account(?: number| no\.?)?:\s*[\dX*\- ]*?(\d{4})\b", re.IGNORECASE)
_ENDING_RE = re.compile(r"ending(?: in)?\s+(\d{4})\b", re.IGNORECASE)
_HOLDER_RE = re.compile(r"^\s*Account (?:name|holder):\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_AMOUNT_RE = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")
_INVOICE_RE = re.compile(r"\b(?!PO-)([A-Z]{2,4}-\d[\d-]*\d)\b")
_PO_RE = re.compile(r"\b(PO-\d{4}-\d{4})\b")
_REMIT_RE = re.compile(r"^\s*Remit(?:-| )to:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

_GIFT_CARD_RE = re.compile(r"gift ?cards?|itunes card|google play card|steam card", re.IGNORECASE)
_SENSITIVE_RE = re.compile(r"\bW-?2s?\b|employee records|social security|\bSSNs?\b|payroll records", re.IGNORECASE)


def _first(rx: re.Pattern, text: str) -> str | None:
    m = rx.search(text)
    return m.group(1) if m else None


def _method(text: str) -> str | None:
    # "wire" anywhere wins: a request to switch to wire usually also mentions ACH.
    if re.search(r"\bwire\b", text, re.IGNORECASE):
        return "wire"
    if re.search(r"\bACH\b", text):
        return "ACH"
    return None


def extract_payment_details(text: str) -> PaymentDetails:
    amounts = [Decimal(a.replace(",", "")) for a in _AMOUNT_RE.findall(text)]
    return PaymentDetails(
        bank_name=_first(_BANK_RE, text),
        routing_number=_first(_ROUTING_RE, text),
        account_last4=_first(_ACCOUNT_RE, text) or _first(_ENDING_RE, text),
        account_holder=_first(_HOLDER_RE, text),
        method=_method(text),
        amount=max(amounts) if amounts else None,
        invoice_number=_first(_INVOICE_RE, text),
        po=_first(_PO_RE, text),
        remit_to=_first(_REMIT_RE, text),
    )


def find_vendor(e: Email, ledger: VendorLedger) -> Vendor | None:
    """The vendor this email is about: by sender domain, else by a vendor or contact name in the display name."""
    for v in ledger.vendors:
        if e.from_domain in v.domains:
            return v
    name = e.from_name.strip().lower()
    for v in ledger.vendors:
        if name and (name == v.name.lower() or any(name == c.name.lower() for c in v.contacts)):
            return v
    return None


def _sig(code, verdict, message, weight="none") -> Signal:
    return Signal(code=code, group="content", verdict=verdict, weight=weight, message=message, source="rules (ledger)")


def compare_to_ledger(d: PaymentDetails, v: Vendor) -> list[Signal]:
    out: list[Signal] = []
    on_file = v.bank_account
    uses = sum(1 for i in v.past_invoices if i.status == "paid" and i.bank_last4 == on_file.account_last4)

    changed = (
        (d.account_last4 and d.account_last4 != on_file.account_last4)
        or (d.routing_number and d.routing_number != on_file.routing_number)
        or (d.bank_name and d.bank_name.lower() != on_file.bank_name.lower())
    )
    if changed:
        new = f"ending {d.account_last4}" if d.account_last4 else f"at {d.bank_name or 'a different bank'}"
        where = f" in {d.found_in}" if d.found_in else ""
        out.append(_sig("bank_change", "unusual",
                        f"New bank account {new}{where} (previously {on_file.account_last4}, used on {uses} invoices)",
                        "strong"))
    elif d.account_last4:
        out.append(_sig("bank_account_matches", "fine", f"Bank account ending {d.account_last4} matches the one on file"))

    if d.account_holder and d.account_holder.lower() != on_file.account_holder.lower():
        out.append(_sig("holder_change", "unusual",
                        f'Account holder "{d.account_holder}" differs from "{on_file.account_holder}" on file', "medium"))

    if d.method and d.method != v.payment_method:
        out.append(_sig("method_change", "unusual", f"Asks to switch from {v.payment_method} to {d.method}", "medium"))

    if d.amount is not None:
        r = v.usual_amount
        if r.min <= d.amount <= r.max:
            out.append(_sig("amount_in_range", "fine", f"Amount (${d.amount:,.2f}) is within {v.name}'s usual range"))
        else:
            out.append(_sig("amount_out_of_range", "unusual",
                            f"Amount (${d.amount:,.2f}) is outside {v.name}'s usual ${r.min:,.0f}–${r.max:,.0f}", "medium"))

    on_record = next((i for i in v.past_invoices if i.number == d.invoice_number), None)
    if on_record and on_record.status == "open":
        out.append(_sig("invoice_open_on_file", "fine", f"Invoice {on_record.number} is an open invoice in your records"))
    elif on_record:
        out.append(_sig("invoice_already_paid", "unusual",
                        f"Invoice {on_record.number} was already paid on {on_record.date:%b %d, %Y}", "medium"))
    elif d.invoice_number:
        if re.match(v.invoice_pattern, d.invoice_number):
            out.append(_sig("invoice_format_ok", "fine", f"Invoice number {d.invoice_number} matches {v.name}'s format"))
        else:
            out.append(_sig("invoice_format", "unusual",
                            f"Invoice number {d.invoice_number} does not match {v.name}'s usual format", "low"))

    if not d.po and not (on_record and on_record.po) and any(i.po for i in v.past_invoices):
        out.append(_sig("po_missing", "unusual", f"No PO number, though {v.name}'s invoices usually have one", "low"))

    if d.found_in:
        out = [s.model_copy(update={"source": "rules (ledger) on fields read by Nemotron Super VL"}) for s in out]
    return out


def check_request_keywords(text: str) -> list[Signal]:
    out: list[Signal] = []
    if _GIFT_CARD_RE.search(text):
        out.append(_sig("gift_card_request", "unusual", "Asks for gift cards, a common scam payment method", "strong"))
    if _SENSITIVE_RE.search(text):
        out.append(_sig("sensitive_data_request", "unusual", "Asks for W-2s or employee records", "strong"))
    return [s.model_copy(update={"source": "rules (keywords)"}) for s in out]


# ---------- Language (Nemotron Super) ----------

LANGUAGE_SYSTEM = (
    "You review a business email for manipulation tactics. Reply with JSON only: "
    '{"urgency": bool, "secrecy": bool, "pressure": bool, "channel_switch": bool, "unusual_request": bool, '
    '"quotes": [short exact phrases from the email that show these, max 3]}. '
    "urgency: demands action today/now. secrecy: asks to keep it quiet or not involve others. "
    "pressure: threats, penalties, authority pressure. channel_switch: asks to move to text, WhatsApp, a personal "
    "email, or a phone number given in the email. unusual_request: a request type a vendor or colleague rarely makes."
)


class LanguageOut(BaseModel):
    urgency: bool = False
    secrecy: bool = False
    pressure: bool = False
    channel_switch: bool = False
    unusual_request: bool = False
    quotes: list[str] = []


def _llm_sig(code, message, weight, source="Nemotron Super") -> Signal:
    return Signal(code=code, group="content", verdict="unusual", weight=weight, message=message, source=source)


def language_signals(out: LanguageOut) -> list[Signal]:
    q = f'"{out.quotes[0]}"' if out.quotes else None
    signals: list[Signal] = []
    rushed = out.urgency or out.pressure
    if rushed and out.secrecy:  # brief §6.3: urgency+secrecy is ONE medium signal
        signals.append(_llm_sig("urgency_secrecy", f"{q} pushes for speed and secrecy" if q else
                                "Pushes for speed and secrecy", "medium"))
    elif rushed:
        signals.append(_llm_sig("time_pressure", f"{q} adds time pressure" if q else "Adds time pressure", "low"))
    elif out.secrecy:
        signals.append(_llm_sig("secrecy", f"{q} asks to keep this quiet" if q else "Asks to keep this quiet", "low"))
    if out.channel_switch:
        signals.append(_llm_sig("channel_switch", "Asks to move the conversation to another channel", "low"))
    if out.unusual_request:
        signals.append(_llm_sig("unusual_request", "Unusual type of request for this sender", "low"))
    return signals


async def check_language(e: Email) -> list[Signal]:
    out = await complete_json(
        step="language", key=e.message_id, model=load_settings().model_super,
        messages=[{"role": "system", "content": LANGUAGE_SYSTEM},
                  {"role": "user", "content": f"Subject: {e.subject}\n\n{e.body_text[:4000]}"}],
        schema=LanguageOut, default=LanguageOut(),
    )
    return language_signals(out)


# ---------- Writing style (Nemotron Super, soft signal) ----------

STYLE_SYSTEM = (
    "Compare the NEW email's writing style (greeting, sign-off, tone, phrasing, formatting) with PAST emails from "
    'the same sender. Ignore topic differences. Reply with JSON only: {"mismatch": bool, "reason": "short phrase"}.'
)
MAX_STYLE_HISTORY = 5  # brief §6.2


class StyleOut(BaseModel):
    mismatch: bool = False
    reason: str = ""


def style_signals(out: StyleOut) -> list[Signal]:
    if out.mismatch:
        return [_llm_sig("style_mismatch", f"Writing style differs from past emails ({out.reason})", "low")]
    return [Signal(code="style_ok", group="content", verdict="fine", source="Nemotron Super",
                   message="Writing style matches past emails from this sender")]


async def check_style(e: Email, vendor: Vendor | None) -> list[Signal]:
    past = [p for p in (vendor.past_emails if vendor else []) if p.from_addr == e.from_addr][:MAX_STYLE_HISTORY]
    if not past:
        return []  # no history: first_contact already says so
    history = "\n\n---\n\n".join(p.body for p in past)
    out = await complete_json(
        step="style", key=e.message_id, model=load_settings().model_super,
        messages=[{"role": "system", "content": STYLE_SYSTEM},
                  {"role": "user", "content": f"PAST EMAILS:\n{history}\n\nNEW EMAIL:\n{e.body_text[:4000]}"}],
        schema=StyleOut, default=StyleOut(),
    )
    return style_signals(out)


# ---------- Payment details from attachments (Nemotron Super VL) ----------

VL_SYSTEM = (
    "Read this invoice or remittance document. Reply with JSON only: "
    '{"bank_name", "routing_number", "account_number", "account_holder", "method" ("ACH", "wire" or "check"), '
    '"amount" (number as string), "invoice_number", "po", "remit_to"} using null for anything not shown.'
)
MAX_PAGES = 3      # arbitrary; enough for an invoice + remittance page
RENDER_SCALE = 2   # 144 dpi: legible digits; measured PNG 1224x1584, 73 KB for scenario 7
IMAGE_TYPES = {"image/png", "image/jpeg"}


class VLOut(BaseModel):
    bank_name: str | None = None
    routing_number: str | None = None
    account_number: str | None = None
    account_holder: str | None = None
    method: str | None = None
    amount: str | None = None
    invoice_number: str | None = None
    po: str | None = None
    remit_to: str | None = None


def render_pages(a: Attachment) -> list[bytes]:
    """PDF -> PNG bytes per page (pypdfium2 renders, Pillow encodes). Images pass through."""
    if a.content_type in IMAGE_TYPES:
        return [a.data]
    pages = []
    doc = pdfium.PdfDocument(a.data)
    for i in range(min(len(doc), MAX_PAGES)):
        buf = io.BytesIO()
        doc[i].render(scale=RENDER_SCALE).to_pil().save(buf, format="PNG")
        pages.append(buf.getvalue())
    return pages


def _to_details(v: VLOut, filename: str) -> PaymentDetails:
    digits = re.sub(r"\D", "", v.account_number or "")
    method = (v.method or "").lower()
    amount = re.sub(r"[^\d.]", "", v.amount or "")
    return PaymentDetails(
        bank_name=v.bank_name, routing_number=re.sub(r"\D", "", v.routing_number or "") or None,
        account_last4=digits[-4:] if len(digits) >= 4 else None, account_holder=v.account_holder,
        method="wire" if "wire" in method else "ACH" if "ach" in method else "check" if "check" in method else None,
        amount=Decimal(amount) if amount else None, invoice_number=v.invoice_number, po=v.po, remit_to=v.remit_to,
        found_in=filename,
    )


async def extract_from_attachments(e: Email) -> PaymentDetails | None:
    docs = [a for a in e.attachments if a.content_type == "application/pdf" or a.content_type in IMAGE_TYPES]
    if not docs:
        return None
    a = docs[0]  # first document only: keeps VL cost to one call per email
    try:
        pages = render_pages(a)
    except Exception:  # corrupt PDF: skip rather than fail the whole check
        return None
    media = "image/jpeg" if a.content_type == "image/jpeg" else "image/png"
    content = [{"type": "text", "text": f"Document: {a.filename}"}] + [
        {"type": "image_url", "image_url": {"url": f"data:{media};base64,{base64.b64encode(p).decode()}"}}
        for p in pages]
    out = await complete_json(
        step="vl", key=e.message_id, model=load_settings().model_vl,
        messages=[{"role": "system", "content": VL_SYSTEM}, {"role": "user", "content": content}],
        schema=VLOut, default=VLOut(),
    )
    return _to_details(out, a.filename)


def merge_details(body: PaymentDetails, attachment: PaymentDetails | None) -> PaymentDetails:
    """Attachment fields win: the attachment is usually where the payment instruction is."""
    if attachment is None:
        return body
    return body.model_copy(update={k: v for k, v in attachment.model_dump().items() if v is not None})
