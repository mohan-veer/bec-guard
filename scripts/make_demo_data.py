"""Builds the live demo dataset for tenant "riverbend" from ONE definition, so mailbox history and vendor records agree.

Writes:
  data/tenants/riverbend/vendor_ledger.json   vendor master data (in production: the accounting system)
  data/tenants/riverbend/org_directory.json   people on file
  fixtures/demo/riverbend_history.json        ~22 backdated emails (Jun–Oct 2026) for the add-on's seedDemoHistory()
  demo-emails/<scenario>/                     the live test emails to send by hand: email.txt + the PDF to attach

Run: .venv/bin/python scripts/make_demo_data.py   (tests/test_demo_data.py fails if the outputs are stale)
See docs/DEMO_SCENARIOS.md for the story and the test cases.
"""
import base64
import json
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.phase_a.models import OrgDirectory, VendorLedger  # noqa: E402
from scenarios.make_pdf_scenario import make_pdf  # noqa: E402

TENANT = "riverbend"

# ---------- people and accounts ----------

ORG_NAME = "Riverbend Dental Partners"
JORDAN = ("Jordan Ellis", "testorganization26@gmail.com")   # our test mailbox (AP clerk)
SAM = ("Sam Ortiz", "test.vendor26@yahoo.com")              # our test mailbox (vendor)
DANA = ("Dana Whitfield", "dana.whitfield@riverbend.example")
PRIYA = ("Priya Raman", "priya.raman@riverbend.example")
MARCUS = ("Marcus Lee", "marcus.lee@riverbend.example")
ALEX = ("Alex Kim", "frontdesk@riverbend.example")
PACIFIC = ("Mei Chen", "orders@pacificpaper.example")
BRIGHT = ("Alicia Grant", "office@brightclean.example")
SUMMIT = ("Raj Patel", "support@summitit.example")
DESK = ("DentalDesk", "noreply@dentaldesk.example")
DIGEST = ("Pacific Dental Digest", "digest@dentaldigest.example")

PEOPLE = [
    {"name": DANA[0], "role": "CEO", "email": DANA[1], "phone": "(503) 555-0110"},
    {"name": PRIYA[0], "role": "CFO", "email": PRIYA[1], "phone": "(503) 555-0111"},
    {"name": MARCUS[0], "role": "HR Lead", "email": MARCUS[1], "phone": "(503) 555-0112"},
    {"name": JORDAN[0], "role": "AP Clerk", "email": JORDAN[1], "phone": "(503) 555-0113"},
    {"name": ALEX[0], "role": "Front Desk", "email": ALEX[1], "phone": "(503) 555-0114"},
]

ACME_BANK = {"bank_name": "First Cascade Bank", "routing_number": "999000111", "account_last4": "4821",
             "account_holder": "Acme Supply LLC"}

# number, date, amount, PO, status. ACM-10435..10437 are also in the mailbox (with PDFs); older ones predate it.
ACME_INVOICES = [
    ("ACM-10431", "2026-02-03", 14250.00, "PO-2026-0071", "paid"),
    ("ACM-10432", "2026-03-03", 17900.00, "PO-2026-0080", "paid"),
    ("ACM-10433", "2026-04-01", 12600.00, "PO-2026-0089", "paid"),
    ("ACM-10434", "2026-05-01", 21300.00, "PO-2026-0094", "paid"),
    ("ACM-10435", "2026-07-01", 16450.00, "PO-2026-0101", "paid"),
    ("ACM-10436", "2026-09-01", 19800.00, "PO-2026-0111", "paid"),
    ("ACM-10437", "2026-10-01", 18400.00, "PO-2026-0118", "open"),
]

OTHER_VENDORS = [
    {"id": "pacificpaper", "name": "Pacific Paper Co", "contact": PACIFIC, "domain": "pacificpaper.example",
     "phone": "(503) 555-0163", "bank": ("Willamette Valley Bank", "999000333", "5567", "Pacific Paper Company"),
     "range": (800, 2000), "pattern": r"^PPC-\d{4}-\d{4}$",
     "invoices": [("PPC-2026-0409", "2026-07-08", 960.00, "PO-2026-0098")]},
    {"id": "brightclean", "name": "BrightClean Janitorial", "contact": BRIGHT, "domain": "brightclean.example",
     "phone": "(503) 555-0129", "bank": ("Columbia Community Bank", "999000444", "3408", "BrightClean Janitorial LLC"),
     "range": (2200, 2600), "pattern": r"^BC-\d{5}$",
     "invoices": [("BC-20871", "2026-07-31", 2400.00, None)]},
    {"id": "summitit", "name": "Summit IT Services", "contact": SUMMIT, "domain": "summitit.example",
     "phone": "(360) 555-0171", "bank": ("Pacific Northwest Credit Union", "999000555", "9012", "Summit IT Services Inc."),
     "range": (3000, 6000), "pattern": r"^SIT-\d{4}$",
     "invoices": [("SIT-1233", "2026-09-01", 5240.00, "PO-2026-0109")]},
]


def acme_invoice_pdf(number: str) -> bytes:
    n, date, amount, po, _ = next(i for i in ACME_INVOICES if i[0] == number)
    return make_pdf([
        "ACME SUPPLY LLC - INVOICE",
        "1200 Industrial Way, Portland, OR 97210",
        f"Invoice number: {n}",
        f"Invoice date: {date}",
        f"Bill to: {ORG_NAME}",
        f"Purchase order: {po}",
        "Description: Clinical and office supplies (monthly order)",
        f"Amount due: ${amount:,.2f}",
        "Terms: Net 30",
        f"Pay by ACH to the account on file: {ACME_BANK['bank_name']}, account ending {ACME_BANK['account_last4']}",
    ])


def acme_setup_pdf() -> bytes:
    b = ACME_BANK
    return make_pdf([
        "ACME SUPPLY LLC - VENDOR INFORMATION SHEET",
        "Legal name: Acme Supply LLC",
        "Remit-to: 1200 Industrial Way, Portland, OR 97210",
        "Accounts receivable: Sam Ortiz, (503) 555-0142",
        "Preferred payment method: ACH",
        f"Bank: {b['bank_name']}",
        f"Routing number: {b['routing_number']}",
        f"Account: ending {b['account_last4']}",
        f"Account holder: {b['account_holder']}",
    ])


def _inv_body(number: str, po: str, extra: str) -> str:
    return (f"Hi Jordan,\n\nAttached is invoice {number} for {po}, net 30. {extra}\n\n"
            "Thanks,\nSam Ortiz\nAccounts Receivable, Acme Supply")


# ---------- the mailbox history ----------
# (key, date, sender, recipients, subject, body, attachments, labels, reply_to_key)
INV = {i[0]: i for i in ACME_INVOICES}

HISTORY = [
    ("acme-setup", "Wed, 10 Jun 2026 09:14:00 -0700", SAM, [JORDAN], "Acme Supply: vendor setup",
     "Hi Jordan,\n\nThanks for choosing Acme Supply. Attached is our vendor information sheet with our remittance "
     "details. We're paid by ACH to the account ending 4821.\n\nThanks,\nSam Ortiz\nAccounts Receivable, Acme Supply",
     [("Acme-Supply-Vendor-Info.pdf", "setup")], ["INBOX"], None),
    ("acme-setup-reply", "Wed, 10 Jun 2026 11:02:00 -0700", JORDAN, [SAM], "Re: Acme Supply: vendor setup",
     "Hi Sam,\n\nThanks, you're set up in our system with ACH to the account ending 4821.\n\nJordan Ellis\nAccounts Payable, "
     "Riverbend Dental Partners", [], ["SENT"], "acme-setup"),
    ("ceo-june", "Mon, 15 Jun 2026 08:30:00 -0700", DANA, [JORDAN, PRIYA, MARCUS, ALEX], "June update",
     "Hi team,\n\nGreat first half of the year: patient visits are up 8% and the new hygiene room opens in July. "
     "Thank you all.\n\nDana", [], ["INBOX"], None),
    ("desk-june", "Sat, 20 Jun 2026 06:00:00 -0700", DESK, [JORDAN], "Your weekly schedule summary",
     "DentalDesk weekly summary for Riverbend Dental Partners: 142 appointments booked, 6 cancellations.\n\n"
     "This is an automated message from DentalDesk.", [], ["INBOX"], None),
    ("acme-10435", "Wed, 01 Jul 2026 09:05:00 -0700", SAM, [JORDAN], "Invoice ACM-10435",
     _inv_body("ACM-10435", INV["ACM-10435"][3], "ACH to the usual account is fine."),
     [("ACM-10435.pdf", "ACM-10435")], ["INBOX"], None),
    ("acme-10435-reply", "Thu, 02 Jul 2026 10:20:00 -0700", JORDAN, [SAM], "Re: Invoice ACM-10435",
     "Hi Sam,\n\nPaid today via ACH to the account ending 4821.\n\nJordan", [], ["SENT"], "acme-10435"),
    ("pacific-0409", "Wed, 08 Jul 2026 13:40:00 -0700", PACIFIC, [JORDAN], "Invoice PPC-2026-0409",
     "Hi Jordan,\n\nInvoice PPC-2026-0409 for PO-2026-0098: $960.00, net 30, ACH to the account on file.\n\n"
     "Best,\nMei Chen\nPacific Paper Co", [], ["INBOX"], None),
    ("hr-enrollment", "Wed, 15 Jul 2026 09:00:00 -0700", MARCUS, [JORDAN, PRIYA, ALEX], "Benefits open enrollment",
     "Hi all,\n\nOpen enrollment for dental and vision benefits runs July 20-31. Forms are in the shared drive.\n\n"
     "Marcus", [], ["INBOX"], None),
    ("bright-july", "Fri, 31 Jul 2026 16:10:00 -0700", BRIGHT, [JORDAN], "July cleaning invoice",
     "Hi there,\n\nHere is the July invoice BC-20871: $2,400.00. Thanks for your business.\n\nAlicia\n"
     "BrightClean Janitorial", [], ["INBOX"], None),
    ("digest-aug", "Mon, 03 Aug 2026 07:00:00 -0700", DIGEST, [JORDAN], "This week in dental practice management",
     "Top stories: staffing trends for 2027, new sterilization guidelines, and how small practices cut supply costs.\n\n"
     "You are receiving this newsletter from Pacific Dental Digest.", [], ["INBOX"], None),
    ("acme-delivery", "Tue, 18 Aug 2026 10:45:00 -0700", SAM, [JORDAN], "Delivery schedule for September",
     "Hi Jordan,\n\nHeads up: our September deliveries move to Tuesdays because of a warehouse change. "
     "No change to invoicing or payment.\n\nThanks,\nSam Ortiz\nAccounts Receivable, Acme Supply",
     [], ["INBOX"], None),
    ("acme-delivery-reply", "Tue, 18 Aug 2026 12:03:00 -0700", JORDAN, [SAM], "Re: Delivery schedule for September",
     "Thanks Sam, noted. Tuesdays work for us.\n\nJordan", [], ["SENT"], "acme-delivery"),
    ("cfo-budget", "Sat, 22 Aug 2026 09:15:00 -0700", PRIYA, [JORDAN], "Q3 supply budget",
     "Hi Jordan,\n\nReminder that Q3 supply spend is capped at $60k. Acme is our biggest line; flag anything unusual.\n\n"
     "Priya", [], ["INBOX"], None),
    ("acme-10436", "Tue, 01 Sep 2026 09:02:00 -0700", SAM, [JORDAN], "Invoice ACM-10436",
     _inv_body("ACM-10436", INV["ACM-10436"][3], "Let me know if you need anything else."),
     [("ACM-10436.pdf", "ACM-10436")], ["INBOX"], None),
    ("acme-10436-reply", "Thu, 03 Sep 2026 15:30:00 -0700", JORDAN, [SAM], "Re: Invoice ACM-10436",
     "Hi Sam,\n\nPaid via ACH today.\n\nJordan", [], ["SENT"], "acme-10436"),
    ("summit-maint", "Sat, 12 Sep 2026 08:00:00 -0700", SUMMIT, [JORDAN, ALEX], "Planned maintenance Sunday 9/13",
     "Hello,\n\nWe'll patch the office firewall and Wi-Fi this Sunday 6-8 AM. Expect brief outages.\n\n"
     "Raj Patel\nSummit IT Services", [], ["INBOX"], None),
    ("frontdesk-friday", "Sat, 26 Sep 2026 17:20:00 -0700", ALEX, [JORDAN], "Front desk coverage Friday",
     "Hi Jordan, could you cover the front desk Friday 12-1 while I'm at lunch with a patient's family? Thanks! Alex",
     [], ["INBOX"], None),
    ("acme-10437", "Thu, 01 Oct 2026 09:10:00 -0700", SAM, [JORDAN], "Invoice ACM-10437",
     _inv_body("ACM-10437", INV["ACM-10437"][3], "ACH to the usual account is fine."),
     [("ACM-10437.pdf", "ACM-10437")], ["INBOX"], None),
    ("acme-10437-reply", "Fri, 02 Oct 2026 11:00:00 -0700", JORDAN, [SAM], "Re: Invoice ACM-10437",
     "Hi Sam,\n\nReceived, thanks. It's scheduled for our October 30 payment run.\n\nJordan", [], ["SENT"], "acme-10437"),
    ("ceo-lunch", "Fri, 09 Oct 2026 08:45:00 -0700", DANA, [JORDAN, PRIYA, MARCUS, ALEX], "Team lunch next Thursday",
     "Hi everyone,\n\nTeam lunch next Thursday at noon, my treat. Reply with any dietary needs.\n\nDana",
     [], ["INBOX"], None),
    ("digest-oct", "Fri, 16 Oct 2026 07:00:00 -0700", DIGEST, [JORDAN], "Fraud alert: payment scams target small practices",
     "This week: business email compromise is up again. Always confirm bank changes by phone using a number you "
     "already have.\n\nYou are receiving this newsletter from Pacific Dental Digest.", [], ["INBOX"], None),
    ("desk-oct", "Tue, 20 Oct 2026 06:00:00 -0700", DESK, [JORDAN], "Your weekly schedule summary",
     "DentalDesk weekly summary for Riverbend Dental Partners: 151 appointments booked, 4 cancellations.\n\n"
     "This is an automated message from DentalDesk.", [], ["INBOX"], None),
]

ACME_STYLE_KEYS = ["acme-10435", "acme-10436", "acme-10437"]  # the vendor's past invoice emails (style comparison)


def _mid(key: str) -> str:
    return f"<{key}@demo.bec-guard.example>"


def _addr(p: tuple[str, str]) -> str:
    return f"{p[0]} <{p[1]}>"


def _attachment(kind: str) -> bytes:
    return acme_setup_pdf() if kind == "setup" else acme_invoice_pdf(kind)


def build_message(item) -> EmailMessage:
    key, date, sender, to, subject, body, attachments, _, reply_to_key = item
    msg = EmailMessage()
    msg["Message-ID"] = _mid(key)
    if reply_to_key:
        msg["In-Reply-To"] = _mid(reply_to_key)
        msg["References"] = _mid(reply_to_key)
    msg["Date"] = date
    msg["From"] = _addr(sender)
    msg["To"] = ", ".join(_addr(p) for p in to)
    msg["Subject"] = subject
    msg["X-BEC-Guard-Demo"] = "seeded-history"  # imported history, not delivered mail (see docs/DEMO_SCENARIOS.md)
    msg.set_content(body)
    for filename, kind in attachments:
        msg.add_attachment(_attachment(kind), maintype="application", subtype="pdf", filename=filename)
    if attachments:
        msg.set_boundary(f"bec-guard-demo-{key}")  # deterministic output
    return msg


def _ledger() -> dict:
    by_key = {h[0]: h for h in HISTORY}
    acme = {
        "id": "acme", "name": "Acme Supply", "domains": [], "official_website": "", "official_phone": "(503) 555-0142",
        "contacts": [{"name": SAM[0], "email": SAM[1], "role": "Accounts Receivable"}],
        "bank_account": ACME_BANK, "payment_method": "ACH", "usual_amount": {"min": 12000, "max": 25000},
        "invoice_pattern": r"^ACM-\d{5}$", "remit_to": "1200 Industrial Way, Portland, OR 97210",
        "past_invoices": [{"number": n, "date": d, "amount": a, "po": po, "bank_last4": ACME_BANK["account_last4"],
                           "method": "ACH", "status": s} for n, d, a, po, s in ACME_INVOICES],
        "past_emails": [{"from_addr": SAM[1], "date": _iso(by_key[k][1]), "subject": by_key[k][4], "body": by_key[k][5]}
                        for k in ACME_STYLE_KEYS],
    }
    others = []
    for v in OTHER_VENDORS:
        bank, routing, last4, holder = v["bank"]
        others.append({
            "id": v["id"], "name": v["name"], "domains": [v["domain"]], "official_website": "",
            "official_phone": v["phone"], "contacts": [{"name": v["contact"][0], "email": v["contact"][1], "role": "Billing"}],
            "bank_account": {"bank_name": bank, "routing_number": routing, "account_last4": last4, "account_holder": holder},
            "payment_method": "ACH", "usual_amount": {"min": v["range"][0], "max": v["range"][1]},
            "invoice_pattern": v["pattern"], "remit_to": "",
            "past_invoices": [{"number": n, "date": d, "amount": a, "po": po, "bank_last4": last4, "method": "ACH",
                               "status": "paid"} for n, d, a, po in v["invoices"]],
            "past_emails": [],
        })
    ledger = {"_note": "LIVE DEMO PROFILE (tenant 'riverbend'), generated by scripts/make_demo_data.py. Vendor master "
                       "data; in production this comes from the accounting system. Fictional: routing numbers start "
                       "with 999, phones 555-01xx, other vendors on reserved .example domains.",
              "vendors": [acme] + others}
    VendorLedger.model_validate(ledger)
    return ledger


def _iso(rfc_date: str) -> str:
    from email.utils import parsedate_to_datetime
    return parsedate_to_datetime(rfc_date).date().isoformat()


def build() -> dict:
    org = {"_note": "LIVE DEMO PROFILE (tenant 'riverbend'), generated by scripts/make_demo_data.py. "
                    "testorganization26@gmail.com is our own test mailbox; @riverbend.example is a reserved domain.",
           "org_name": ORG_NAME, "domains": ["riverbend.example"], "people": PEOPLE}
    OrgDirectory.model_validate(org)
    messages = [{"key": item[0], "labels": item[7],
                 "raw": base64.urlsafe_b64encode(bytes(build_message(item))).decode().rstrip("=")}
                for item in HISTORY]
    return {"ledger": _ledger(), "org": org,
            "history": {"_note": "Backdated demo history for testorganization26@gmail.com. Imported by the add-on's "
                                 "seedDemoHistory(); every message carries X-BEC-Guard-Demo: seeded-history.",
                        "tenant": TENANT, "messages": messages}}


def outputs(built: dict) -> dict[str, str]:
    dump = lambda obj: json.dumps(obj, indent=2) + "\n"  # noqa: E731
    return {f"data/tenants/{TENANT}/vendor_ledger.json": dump(built["ledger"]),
            f"data/tenants/{TENANT}/org_directory.json": dump(built["org"]),
            f"fixtures/demo/{TENANT}_history.json": dump(built["history"])}




# ---------- live test emails (sent by hand during the demo; see docs/DEMO_SCENARIOS.md) ----------
# Each gets a folder under demo-emails/ with email.txt (from / to / subject / body) and the PDF to attach.

def _invoice_lines(number, date, amount, po, bank, routing, account, method):
    return ["ACME SUPPLY LLC - INVOICE", "1200 Industrial Way, Portland, OR 97210",
            f"Invoice number: {number}", f"Invoice date: {date}", f"Bill to: {ORG_NAME}", f"Purchase order: {po}",
            "Description: Clinical and office supplies (monthly order)", f"Amount due: ${amount:,.2f}", "Terms: Net 30",
            f"Payment method: {method}", f"Bank: {bank}", f"Routing number: {routing}", f"Account number: {account}",
            "Account name: Acme Supply LLC"]


LIVE_EMAILS = [
    ("C1_normal-invoice", SAM[1], "Invoice ACM-10438",
     "Hi Jordan,\n\nAttached is invoice ACM-10438 for PO-2026-0125: $17,200.00, net 30. ACH to the usual account "
     "is fine.\n\nThanks,\nSam Ortiz\nAccounts Receivable, Acme Supply",
     "ACM-10438.pdf",
     ["ACME SUPPLY LLC - INVOICE", "1200 Industrial Way, Portland, OR 97210", "Invoice number: ACM-10438",
      "Invoice date: 2026-10-27", f"Bill to: {ORG_NAME}", "Purchase order: PO-2026-0125",
      "Description: Clinical and office supplies (monthly order)", "Amount due: $17,200.00", "Terms: Net 30",
      f"Pay by ACH to the account on file: {ACME_BANK['bank_name']}, account ending {ACME_BANK['account_last4']}"],
     "No label. Sidebar: \"No issues found\" + what checked out."),
    ("B1_hacked-vendor-changes-bank", SAM[1], "Re: Invoice ACM-10437",
     "Hi Jordan,\n\nQuick update: we moved our banking. Please use our new account for ACM-10437 ($18,400.00):\n\n"
     "Bank: Pacific Crest Bank\nRouting: 999000222\nAccount: 000058127731\n\nThe updated invoice is attached. "
     "Please process today, by wire.\n\nThanks,\nSam",
     "ACM-10437-updated.pdf",
     _invoice_lines("ACM-10437", "2026-10-01", 18400.00, "PO-2026-0118", "Pacific Crest Bank", "999000222",
                    "000058127731", "Wire transfer"),
     "Red label. Sender checks PASS (real account); new account ending 7731 (on file 4821), ACH -> wire."),
    ("B1b_hacked-vendor-bank-in-pdf", SAM[1], "Re: Invoice ACM-10437",
     "Hi Jordan,\n\nPlease see the attached updated remittance details for ACM-10437 and use them for this "
     "payment.\n\nThanks,\nSam",
     "ACM-10437-remittance.pdf",
     _invoice_lines("ACM-10437", "2026-10-01", 18400.00, "PO-2026-0118", "Pacific Crest Bank", "999000222",
                    "000058127731", "Wire transfer"),
     "REAL MODELS ONLY (Nemotron Super VL reads the PDF). Red label: new account ending 7731 found in the PDF."),
    ("A1_fake-vendor-new-bank-account", "testvendor.26@outlook.com (display name: Sam Ortiz)", "Invoice ACM-10437 - urgent",
     "Hi Jordan,\n\nOur bank flagged the ACH for ACM-10437. Please send the $18,400.00 today by wire to our new "
     "account:\n\nBank: Lakeshore Commerce Bank\nRouting: 999000666\nAccount: 000044019055\n\nCorrected invoice "
     "attached.\n\nThanks,\nSam",
     "ACM-10437.pdf",
     _invoice_lines("ACM-10437", "2026-10-01", 18400.00, "PO-2026-0118", "Lakeshore Commerce Bank", "999000666",
                    "000044019055", "Wire transfer"),
     "Red label (may land in Spam). Address lookalike of test.vendor26@yahoo.com, known name new address, "
     "first contact, new account ending 9055, ACH -> wire."),
]


LIVE_EMAILS.append(
    ("A3_stranger-claims-known-supplier", "testvendor.26@outlook.com (display name: Henry Schein Billing)",
     "New supplier account: Henry Schein",
     "Hi Jordan,\n\nWe're Henry Schein, your new supplier for dental consumables. Please pay the attached invoice "
     "HS-55120 ($6,480.00) within 3 days to activate your account:\n\nBank: Lakeshore Commerce Bank\n"
     "Routing: 999000666\nAccount: 000044019055\n\nQuestions? Call me directly at (206) 555-0177.\n\n"
     "Thanks,\nHenry Schein Billing",
     "HS-55120.pdf",
     ["HENRY SCHEIN - INVOICE (TEST DOCUMENT, NOT REAL)", "Invoice number: HS-55120", "Invoice date: 2026-10-27",
      f"Bill to: {ORG_NAME}", "Description: New account setup - dental consumables", "Amount due: $6,480.00",
      "Terms: Due in 3 days", "Payment method: Wire transfer", "Bank: Lakeshore Commerce Bank",
      "Routing number: 999000666", "Account number: 000044019055", "Questions: (206) 555-0177"],
     "Red label. Web check (Nemotron Super agent + Tavily): Henry Schein's site is henryschein.com, email from "
     "outlook.com; call-back number from henryschein.com; the (206) number in the email isn't Henry Schein's; "
     "sender not in your records; address also resembles Sam Ortiz's (Acme) - supporting fact only."))


# A4: same attack as A3 with a made-up supplier (no real company's name), safe to show in the video.
LIVE_EMAILS.append(
    ("A4_stranger-claims-new-supplier", "testvendor.26@outlook.com (display name: Quillbrook Dental Supply Billing)",
     "Welcome to Quillbrook Dental Supply - first invoice QDS-30418",
     "Hi Jordan,\n\nThank you for choosing Quillbrook Dental Supply as your new supplier for impression materials and "
     "sterilization pouches. As agreed with your office manager, please pay the attached first invoice QDS-30418 "
     "($4,950.00) by Friday to activate your account and keep the opening discount:\n\nBank: Lakeshore Commerce Bank\n"
     "Routing: 999000666\nAccount: 000044019055\n\nQuestions? Call our billing desk at (206) 555-0188.\n\n"
     "Best regards,\nKaren Mills\nBilling, Quillbrook Dental Supply",
     "QDS-30418.pdf",
     ["QUILLBROOK DENTAL SUPPLY - INVOICE (TEST DOCUMENT, FICTIONAL COMPANY)", "Invoice number: QDS-30418",
      "Invoice date: 2026-10-29", f"Bill to: {ORG_NAME}", "Description: Opening order - impression materials, "
      "sterilization pouches", "Amount due: $4,950.00", "Terms: Due Friday", "Payment method: Wire transfer",
      "Bank: Lakeshore Commerce Bank", "Routing number: 999000666", "Account number: 000044019055",
      "Billing desk: (206) 555-0188"],
     "Red label. Verify before paying (rule: new payee). Says Quillbrook but writes from outlook.com, free Outlook "
     "address, not in your records, not one of your vendors, no official website found, payment to an account with "
     "no record (ending 9055, read from the PDF)."))

def write_live_emails() -> None:
    for folder, sender, subject, body, pdf_name, pdf_lines, expected in LIVE_EMAILS:
        d = ROOT / "demo-emails" / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / "email.txt").write_text(f"From: {sender}\nTo: {JORDAN[1]}\nSubject: {subject}\nAttach: {pdf_name}\n"
                                     f"Expected: {expected}\n\n----- body (copy from here) -----\n{body}\n")
        (d / pdf_name).write_bytes(make_pdf(pdf_lines))
        print(f"wrote demo-emails/{folder}/ ({pdf_name})")


def main() -> None:
    for rel, content in outputs(build()).items():
        (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / rel).write_text(content)
        print(f"wrote {rel}")
    write_live_emails()


if __name__ == "__main__":
    main()
