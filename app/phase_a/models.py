"""Pydantic models for emails, signals, decisions, and the seeded ledger/directory."""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------- Email ----------

class Attachment(BaseModel):
    filename: str
    content_type: str
    data: bytes


class Email(BaseModel):
    message_id: str
    in_reply_to: str | None = None
    subject: str = ""
    from_name: str = ""
    from_addr: str
    reply_to: str | None = None
    to: list[str] = []
    date: datetime | None = None
    body_text: str = ""
    # Results parsed from the Authentication-Results header: "pass", "fail", "none", ... or None if absent.
    spf: str | None = None
    dkim: str | None = None
    dmarc: str | None = None
    attachments: list[Attachment] = []

    @property
    def from_domain(self) -> str:
        return self.from_addr.rsplit("@", 1)[-1].lower()


class PaymentDetails(BaseModel):
    """Payment fields found in the body text (regex) or in an attachment (VL model)."""
    bank_name: str | None = None
    routing_number: str | None = None
    account_last4: str | None = None
    account_holder: str | None = None
    method: Literal["ACH", "wire", "check"] | None = None
    amount: Decimal | None = None
    invoice_number: str | None = None
    po: str | None = None
    remit_to: str | None = None
    found_in: str | None = None   # attachment filename when fields came from the VL model


# ---------- Signals and decisions ----------

class Intent(str, Enum):
    BANK_CHANGE = "bank_change"
    PAYMENT_REQUEST = "payment_request"
    GIFT_CARDS = "gift_cards"
    PAYROLL_CHANGE = "payroll_change"
    DATA_REQUEST = "data_request"
    NONE = "none"


class Decision(str, Enum):
    VERIFY_BEFORE_PAYING = "VERIFY_BEFORE_PAYING"
    LOOKS_UNUSUAL = "LOOKS_UNUSUAL"
    NO_ISSUES_FOUND = "NO_ISSUES_FOUND"


class Signal(BaseModel):
    code: str                     # stable id the scorer keys on, e.g. "lookalike_domain"
    group: Literal["gate", "entity", "org", "content"]
    verdict: Literal["fine", "unusual", "info"]
    weight: Literal["strong", "medium", "low", "none"] = "none"
    message: str                  # one calm line for the result card
    source: str                   # which model or tool produced it, e.g. "rules", "Nemotron Super", "Tavily"
    data: dict = {}               # structured extras for the card, e.g. {"phone": ..., "from": ...}


class ScoreResult(BaseModel):
    decision: Decision
    rule: str                     # name of the scorer rule that decided


class AnalysisResult(BaseModel):
    message_id: str
    intent: Intent
    decision: Decision | None     # None when Gate 0 finds no money or data request
    rule: str | None
    signals: list[Signal]
    explanation: str | None = None  # plain-English summary (Ultra/Super), only for VERIFY / UNUSUAL


# ---------- Seeded data (data/*.json) ----------

class Contact(BaseModel):
    name: str
    email: str
    role: str


class BankAccount(BaseModel):
    bank_name: str
    routing_number: str
    account_last4: str = Field(pattern=r"^\d{4}$")
    account_holder: str


class AmountRange(BaseModel):
    min: Decimal
    max: Decimal


class PastInvoice(BaseModel):
    number: str
    date: date
    amount: Decimal
    po: str | None = None
    bank_last4: str = Field(pattern=r"^\d{4}$")
    method: Literal["ACH", "wire", "check"]
    status: Literal["paid", "open"]


class PastEmail(BaseModel):
    from_addr: str
    date: date
    subject: str
    body: str


class Vendor(BaseModel):
    id: str
    name: str
    domains: list[str]
    official_website: str
    official_phone: str
    contacts: list[Contact]
    bank_account: BankAccount     # the account on file
    payment_method: Literal["ACH", "wire", "check"]
    usual_amount: AmountRange
    invoice_pattern: str          # regex
    remit_to: str
    past_invoices: list[PastInvoice]
    past_emails: list[PastEmail]


class VendorLedger(BaseModel):
    vendors: list[Vendor]


class Person(BaseModel):
    name: str
    role: str
    email: str
    phone: str


class OrgDirectory(BaseModel):
    org_name: str
    domains: list[str]
    people: list[Person]
