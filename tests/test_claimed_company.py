"""Who is the email about? The company it CLAIMS beats a vendor its address merely resembles. Phone numbers are
cross-checked between your records, the company's official website (Super agent + Tavily) and the email itself."""
import asyncio
from pathlib import Path

import pytest

from app.clients import rdap, tavily_client
from app.phase_a import data
from app.phase_a.card import build_card
from app.phase_a.parse import parse_eml
from app.phase_a.pipeline import analyze

SCEN = Path(__file__).parent.parent / "scenarios"
A3 = ("Message-ID: <a3-henry@test>\nFrom: Test Vendor <testvendor.26@outlook.com>\nTo: testorganization26@gmail.com\n"
      "Subject: New supplier account: Henry Schein\n"
      "Authentication-Results: mx.google.com; spf=pass; dkim=pass; dmarc=pass\n\n"
      "Hi Jordan, we're Henry Schein, your new supplier for dental consumables. Please pay the attached invoice "
      "HS-55120 ($6,480.00) within 3 days to activate your account.\nBank: Lakeshore Commerce Bank\n"
      "Routing: 999000666\nAccount: 000044019055\nQuestions? Call me at (206) 555-0177.\nThanks, Henry Schein")


@pytest.fixture(autouse=True)
def _mock(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    rdap._cache.clear()
    tavily_client._cache.clear()


def _run(raw: str | bytes, profile="riverbend"):
    e = parse_eml(raw.encode() if isinstance(raw, str) else raw)
    with data.using_profile(profile):
        r = asyncio.run(analyze(e))
        return r, build_card(r, e)


def _codes(r):
    return {s.code: s for s in r.signals if s.verdict in ("unusual", "fine", "info")}


def test_claimed_company_wins_over_resembled_vendor():
    r, card = _run(A3)
    c = _codes(r)
    # the claimed company was checked on the web (Super agent + Tavily)
    assert c["web_consensus_mismatch"].data["official_domain"] == "henryschein.com"
    # no comparisons against Acme's invoices/amounts (they don't apply to Henry Schein)
    assert not {"amount_out_of_range", "invoice_format", "po_missing", "bank_change"} & set(c)
    # the resemblance to Acme's contact stays, as a supporting fact (not the headline)
    assert c["address_lookalike"].weight == "medium"
    assert c["address_lookalike"].message == ("Not the address your vendor Sam Ortiz (Acme Supply) usually writes from: "
                                              "usually test.vendor26@yahoo.com, this time testvendor.26@outlook.com")
    assert r.rule == "unverified_company"


def test_impostor_card_points_out_facts_and_has_no_call_line():
    _, card = _run(A3)
    assert card.headline == "Verify before paying" and card.action == ""  # no relationship: we don't tell them who to call
    company = [i.text for i in next(s for s in card.sections if s.title == "The company").items]
    assert company[0] == "Says it's Henry Schein, but Henry Schein's website is henryschein.com and this came from outlook.com"
    assert "Henry Schein isn't one of your vendors (no invoices on record)" in company
    request = [i.text for i in next(s for s in card.sections if s.title == "The request").items]
    assert "Asks for payment to a bank account you have no record of (account ending 9055)" in request
    assert card.callback["phone"] == "(800) 555-0123" and card.callback["from"] == "henryschein.com"


def test_sender_signs_with_a_name_that_isnt_in_the_address():
    r, _ = _run(A3.replace("From: Test Vendor <", "From: Henry Schein Billing <"))
    assert _codes(r)["display_name_mismatch"].message == 'Signs as "Henry Schein Billing", but writes from testvendor.26@outlook.com'


def test_phone_in_the_email_is_checked_against_the_official_site():
    r, _ = _run(A3)
    m = _codes(r)["email_phone_mismatch"]
    assert m.verdict == "unusual" and m.weight == "medium"
    assert m.message == "Gives (206) 555-0177 to call, but Henry Schein's website lists (800) 555-0123"


def test_known_vendor_gets_records_first_and_website_cross_check():
    r, card = _run((SCEN / "02_hacked_vendor_thread.eml").read_bytes(), profile="sample")
    assert card.callback["from"] == "your vendor records"
    sources = [cb["from"] for cb in card.callbacks]
    assert sources == ["your vendor records", "acmesupply.com"]
    assert "phones_agree" in _codes(r)


def test_records_and_website_numbers_that_differ_are_noted(monkeypatch):
    from app.phase_a import org
    real = org.find_official_contact

    async def other_number(company, key, text):
        f = await real(company, key, text)
        return f.model_copy(update={"phone": "(503) 555-0199"})
    monkeypatch.setattr(org, "find_official_contact", other_number)
    r, card = _run((SCEN / "02_hacked_vendor_thread.eml").read_bytes(), profile="sample")
    note = _codes(r)["phones_differ"]
    assert note.message == "Acme Supply's website lists (503) 555-0199; your vendor records have (503) 555-0142"
    assert card.callback["phone"] == "(503) 555-0142"  # records stay first


def test_claim_naming_a_vendor_on_file_uses_that_vendor():
    raw = ("Message-ID: <claims-pacific@test>\nFrom: Billing <billing.dept@gmail.com>\nSubject: Invoice\n\n"
           "This is Pacific Paper Co. Please pay PPC-2026-0412 ($1,240.00).\nBank: Other Bank\nRouting: 999000777\n"
           "Account: 000012341234")
    r, _ = _run(raw, profile="sample")
    assert "bank_change" in _codes(r)  # compared with Pacific Paper's account on file (5567)


def test_each_section_leads_with_its_verified_fact():
    _, card = _run(A3)
    first = {s.title: s.items[0].text for s in card.sections}
    assert first["The company"].startswith("Says it's Henry Schein")
    assert first["The request"].startswith("Gives (206) 555-0177")


def test_sender_section_order_name_then_address_then_records_last():
    _, card = _run(A3.replace("From: Test Vendor <", "From: Henry Schein Billing <"))
    codes = [i.code for i in next(s for s in card.sections if s.title == "The sender").items if i.tone == "warn"]
    assert codes[:2] == ["display_name_mismatch", "address_lookalike"] and codes[-1] == "first_contact"


def test_free_email_sender_gets_no_web_address_imitation_line():
    r, _ = _run(A3)
    assert "not_lookalike" not in {s.code for s in r.signals}
