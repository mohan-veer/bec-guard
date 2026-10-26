"""Content checks (rules): payment details vs the ledger, and high-risk request keywords.
LLM language/style checks come later.
"""
import re
from decimal import Decimal

from app.phase_a.models import Email, PaymentDetails, Signal, Vendor, VendorLedger

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
        out.append(_sig("bank_change", "unusual",
                        f"New bank account {new} (previously {on_file.account_last4}, used on {uses} invoices)", "strong"))
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

    return out


def check_request_keywords(text: str) -> list[Signal]:
    out: list[Signal] = []
    if _GIFT_CARD_RE.search(text):
        out.append(_sig("gift_card_request", "unusual", "Asks for gift cards, a common scam payment method", "strong"))
    if _SENSITIVE_RE.search(text):
        out.append(_sig("sensitive_data_request", "unusual", "Asks for W-2s or employee records", "strong"))
    return [s.model_copy(update={"source": "rules (keywords)"}) for s in out]
