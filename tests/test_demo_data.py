"""The live demo dataset: mailbox history and vendor records come from ONE definition, so they always agree."""
import base64
import email
import email.policy
import json
import re
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from scripts import make_demo_data as demo

ROOT = Path(__file__).parent.parent
ORG = "testorganization26@gmail.com"
VENDOR = "test.vendor26@yahoo.com"


@pytest.fixture(scope="module")
def built():
    return demo.build()


def _msgs(built):
    out = []
    for m in built["history"]["messages"]:
        raw = base64.urlsafe_b64decode(m["raw"] + "=" * (-len(m["raw"]) % 4))
        out.append((m, email.message_from_bytes(raw, policy=email.policy.default)))
    return out


def _pdf_text(part):
    doc = pdfium.PdfDocument(part.get_content())
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def test_generated_files_are_up_to_date(built):
    # Run `python scripts/make_demo_data.py` after editing the definition.
    for rel, content in demo.outputs(built).items():
        assert (ROOT / rel).read_text() == content, f"{rel} is stale"


def test_size_and_date_range(built):
    msgs = _msgs(built)
    assert 20 <= len(msgs) <= 25
    dates = [msg["Date"].datetime for _, msg in msgs]
    assert min(dates).month == 6 and max(dates).month == 10 and all(d.year == 2026 for d in dates)


def test_five_vendor_conversations_three_invoices(built):
    vendor_msgs = [msg for _, msg in _msgs(built) if msg["From"].addresses[0].addr_spec == VENDOR]
    threads = {msg["Subject"].removeprefix("Re: ") for msg in vendor_msgs}
    assert len(threads) == 5
    invoices = [msg for msg in vendor_msgs if re.match(r"Invoice ACM-\d{5}$", msg["Subject"])]
    assert [msg["Subject"] for msg in invoices] == ["Invoice ACM-10435", "Invoice ACM-10436", "Invoice ACM-10437"]


def test_every_invoice_pdf_matches_the_ledger(built):
    acme = next(v for v in built["ledger"]["vendors"] if v["id"] == "acme")
    on_file = {i["number"]: i for i in acme["past_invoices"]}
    checked = 0
    for _, msg in _msgs(built):
        for part in msg.iter_attachments():
            text = _pdf_text(part)
            number = re.search(r"Invoice number: (ACM-\d{5})", text)
            if not number:
                continue
            inv = on_file[number.group(1)]
            assert f"${float(inv['amount']):,.2f}" in text
            assert f"ending {acme['bank_account']['account_last4']}" in text
            assert inv["po"] in text
            checked += 1
    assert checked == 3


def test_vendor_setup_sheet_has_the_account_on_file(built):
    acme = next(v for v in built["ledger"]["vendors"] if v["id"] == "acme")
    setup = next(msg for _, msg in _msgs(built) if "vendor setup" in msg["Subject"].lower())
    text = _pdf_text(next(setup.iter_attachments()))
    assert acme["bank_account"]["bank_name"] in text and acme["bank_account"]["routing_number"] in text


def test_open_invoice_is_the_scam_target(built):
    acme = next(v for v in built["ledger"]["vendors"] if v["id"] == "acme")
    open_inv = [i for i in acme["past_invoices"] if i["status"] == "open"]
    assert [i["number"] for i in open_inv] == ["ACM-10437"]
    paid = [i for i in acme["past_invoices"] if i["status"] == "paid" and i["bank_last4"] == "4821"]
    assert len(paid) == 6


def test_ledger_style_history_is_the_vendors_real_invoice_emails(built):
    acme = next(v for v in built["ledger"]["vendors"] if v["id"] == "acme")
    bodies = {msg.get_body(("plain",)).get_content().strip() for _, msg in _msgs(built)
              if msg["From"].addresses[0].addr_spec == VENDOR}
    for past in acme["past_emails"]:
        assert past["body"].strip() in bodies


def test_only_our_accounts_or_reserved_domains(built):
    allowed = {ORG, VENDOR}
    for _, msg in _msgs(built):
        for h in ("From", "To", "Cc", "Reply-To"):
            for a in (msg[h].addresses if msg[h] else []):
                assert a.addr_spec in allowed or a.addr_spec.endswith(".example"), a.addr_spec


def test_clerk_replies_are_sent_mail_and_threaded(built):
    sent = [(m, msg) for m, msg in _msgs(built) if msg["From"].addresses[0].addr_spec == ORG]
    assert sent and all(m["labels"] == ["SENT"] for m, _ in sent)
    assert all(msg["In-Reply-To"] for _, msg in sent)


def test_history_is_marked_as_seeded(built):
    assert all(msg["X-BEC-Guard-Demo"] == "seeded-history" for _, msg in _msgs(built))
    keys = [m["key"] for m in built["history"]["messages"]]
    assert len(keys) == len(set(keys))


def test_live_email_pdfs_match_their_story():
    by = {e[0]: e for e in demo.LIVE_EMAILS}
    text = lambda name: "\n".join(demo.make_pdf(by[name][5]).decode("latin-1").split("\n"))  # noqa: E731
    assert "account ending 4821" in text("Control")                 # happy path: account on file
    assert "000058127731" in text("B1") and "000058127731" in by["B1"][3]   # body and PDF agree
    assert "000058127731" not in by["B1b-pdf-only"][3]                # new account ONLY in the PDF
    assert "000044019055" in text("A1") and "Lakeshore" in by["A1"][3]
