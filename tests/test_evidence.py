"""Evidence from your records under record-based lines (the records equivalent of a web source link)."""
import asyncio

import pytest

from app.clients import rdap, tavily_client
from app.phase_a import data
from app.phase_a.card import build_card
from app.phase_a.content import compare_to_ledger, extract_payment_details
from app.phase_a.parse import parse_eml
from app.phase_a.pipeline import analyze


@pytest.fixture(autouse=True)
def _mock(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    rdap._cache.clear()
    tavily_client._cache.clear()


def _acme():
    with data.using_profile("riverbend"):
        return next(v for v in data.load_ledger().vendors if v.id == "acme")


def test_bank_change_shows_the_invoices_that_used_the_account_on_file():
    d = extract_payment_details("Invoice ACM-10437 ($18,400.00)\nBank: Pacific Crest Bank\nRouting: 999000222\n"
                                "Account: 000058127731")
    bank = next(s for s in compare_to_ledger(d, _acme()) if s.code == "bank_change")
    ev = bank.data["evidence"]
    assert ev["title"] == "From your vendor records · Acme Supply"
    assert ev["headers"] == ["Invoice", "Date", "Amount", "Paid to"]
    assert ev["rows"][:3] == [["ACM-10436", "2026-09-01", "$19,800.00", "••••4821"],
                              ["ACM-10435", "2026-07-01", "$16,450.00", "••••4821"],
                              ["ACM-10434", "2026-05-01", "$21,300.00", "••••4821"]]
    assert ev["rows"][-1] == ["This email", "", "$18,400.00", "••••7731"] and ev["flag_row"] == 3
    assert ev["more"] == "+ 3 earlier, all paid to ••••4821"


def _run(raw: str):
    e = parse_eml(raw.encode())
    with data.using_profile("riverbend"):
        r = asyncio.run(analyze(e))
        return {s.code: s for s in r.signals}, build_card(r, e)


A1 = ("Message-ID: <ev-a1@x>\nFrom: Test Vendor <testvendor.26@outlook.com>\nSubject: Invoice ACM-10437\n\n"
      "Please wire $18,400.00 today.\nBank: Lakeshore Commerce Bank\nRouting: 999000666\nAccount: 000044019055")


def test_address_lookalike_shows_the_contact_on_file_and_their_past_emails():
    s, _ = _run(A1)
    ev = s["address_lookalike"].data["evidence"]
    assert ev["title"] == "From your vendor records · Acme Supply"
    assert ev["rows"] == [["Contact on file", "Sam Ortiz, test.vendor26@yahoo.com"],
                          ["Their past emails", "2026-07-01, 2026-09-01, 2026-10-01"],
                          ["This email", "testvendor.26@outlook.com"]]
    assert ev["flag_row"] == 2


def test_vendor_on_file_shows_a_summary():
    s, _ = _run(A1.replace("testvendor.26@outlook.com", "test.vendor26@yahoo.com"))
    ev = s["vendor_on_file"].data["evidence"]
    assert ["Account on file", "First Cascade Bank ••••4821 (ACH)"] in ev["rows"]
    assert ["Usual amount", "$12,000–$25,000"] in ev["rows"]
    assert ["Invoices on record", "7 (6 paid, 1 open)"] in ev["rows"]


def test_card_items_carry_the_evidence():
    _, card = _run(A1)
    item = next(i for sec in card.sections for i in sec.items if i.code == "bank_change")
    assert item.evidence["flag_row"] == len(item.evidence["rows"]) - 1
