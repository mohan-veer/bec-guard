import asyncio
from pathlib import Path

import pytest

from app.clients import rdap, tavily_client
from app.phase_a.card import build_card
from app.phase_a.models import AnalysisResult, Decision, Intent, Signal
from app.phase_a.parse import parse_eml
from app.phase_a.pipeline import analyze

SCEN = Path(__file__).parent.parent / "scenarios"


@pytest.fixture(autouse=True)
def _mock(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    rdap._cache.clear()
    tavily_client._cache.clear()


def _card(name):
    e = parse_eml((SCEN / name).read_bytes())
    return build_card(asyncio.run(analyze(e)), e)


def _section(card, title):
    return next(s for s in card.sections if s.title == title)


def test_bank_change_card_structure():
    c = _card("02_hacked_vendor_thread.eml")
    assert c.headline == "Verify before paying"
    assert c.intro == "We found the following reasons this email may not be genuine:"
    # a vendor on file is involved: confirm with them on the number from the records (never the email's)
    assert c.action == ("Before paying, confirm the new bank details with Acme Supply at (503) 555-0142 "
                        "(from your vendor records), not a number from this email.")
    assert [s.title for s in c.sections] == ["The sender", "The company", "The request"]
    req = _section(c, "The request").items
    assert req[0].tone == "warn" and req[0].text == ("Asks to pay a new bank account ending 7731; your 6 paid Acme Supply "
                                                     "invoices all went to account ending 4821")
    assert "Asks to switch from ACH to wire" in [i.text for i in req]
    assert [i.tone for i in req] == sorted([i.tone for i in req], key=["warn", "note", "ok"].index)  # warn, note, ok
    assert [cb["from"] for cb in c.callbacks] == ["your vendor records", "acmesupply.com"]
    assert c.explanation is None


def test_lookalike_domain_is_in_the_company_section():
    c = _card("01_lookalike_vendor.eml")
    assert any("Comes from acmesuppIy.com, which imitates acmesupply.com" in i.text for i in _section(c, "The company").items)


def test_internal_person_confirmed_via_staff_directory():
    c = _card("03_fake_ceo_gift_cards.eml")
    assert c.action == ("Before acting, confirm with Dana Whitfield at (503) 555-0110 (from your staff directory), "
                        "not a number from this email.")


def test_no_issues_card():
    c = _card("06_legit_invoice_control.eml")
    assert c.headline == "No issues found" and c.action == ""
    assert c.looks_unusual == []


def test_not_in_records_is_the_last_warning_about_the_sender():
    warns = [i for i in _section(_card("05_fake_supplier_copied_name.eml"), "The sender").items if i.tone == "warn"]
    assert warns[-1].text == "Not in your vendor records or staff directory. New contacts happen, but check them first."


def test_free_provider_sender_is_described_plainly():
    c = _card("03_fake_ceo_gift_cards.eml")
    texts = [i.text for i in _section(c, "The sender").items]
    assert "Sent from a free Gmail address (gmail.com), not a company email" in texts
    assert not any("SPF" in x or "DKIM" in x for x in texts)


def test_known_sender_confirmation_is_listed_as_fine():
    c = _card("06_legit_invoice_control.eml")
    assert "Confirmed as sent from orders@pacificpaperco.com" in c.looks_fine


def test_impersonation_of_vendor_on_file(monkeypatch):
    from app.phase_a import data
    e = parse_eml(b"Message-ID: <a1@x>\nFrom: Test Vendor <testvendor.26@outlook.com>\nSubject: Invoice ACM-10437\n\n"
                  b"Please wire $18,400.00 today.\nBank: Lakeshore Commerce Bank\nRouting: 999000666\nAccount: 000044019055")
    with data.using_profile("riverbend"):
        c = build_card(asyncio.run(analyze(e)), e)
    sender = [i.text for i in _section(c, "The sender").items]
    assert ("Not the address Sam Ortiz usually writes from: usually test.vendor26@yahoo.com, this time "
            "testvendor.26@outlook.com") in sender
    assert c.action.startswith("Before paying, confirm the new bank details with Acme Supply at (503) 555-0142")


def test_no_relationship_means_no_call_line():
    e = parse_eml(b"Message-ID: <x@a.com>\nFrom: A <a@unknown.com>\n\nPay now")
    r = AnalysisResult(message_id="x", intent=Intent.PAYMENT_REQUEST, decision=Decision.VERIFY_BEFORE_PAYING,
                       rule="any_strong_signal", signals=[])
    assert build_card(r, e).action == ""


def test_no_request_card():
    e = parse_eml(b"Message-ID: <x@a.com>\nFrom: a@a.com\n\nLunch?")
    r = AnalysisResult(message_id="x", intent=Intent.NONE, decision=None, rule=None,
                       signals=[Signal(code="intent", group="gate", verdict="info", message="m", source="Nemotron Nano")])
    c = build_card(r, e)
    assert c.headline == "No money or data request found" and c.sections == []


def test_checks_panel_lists_every_check_with_its_source():
    c = _card("07_pdf_bank_details.eml")
    assert all(ch.source for ch in c.checks)
    assert any("Nemotron Super VL" in ch.source for ch in c.checks)
    assert any(ch.source == "Nemotron Nano" for ch in c.checks)


# ---------- Nemotron Ultra wording, checked by code ----------

from app.phase_a.card import accept_rewrite  # noqa: E402


@pytest.mark.parametrize("rewritten,ok", [
    ("The email gives (206) 555-0177, but Henry Schein's website shows (631) 843-5500.", True),
    ("The email gives 206-555-0177, but the website shows (631) 843-5500.", True),          # same numbers, other format
    ("The email gives (206) 555-0199, but the website shows (631) 843-5500.", False),        # changed number
    ("Call (800) 555-1234 instead.", False),                                                  # invented number
    ("The sender's domain is outlook.com.", False),                                           # jargon
    ("word " * 40, False),                                                                    # too long
])
def test_accept_rewrite(rewritten, ok):
    original = "Gives (206) 555-0177 to call, but Henry Schein's website lists (631) 843-5500"
    assert accept_rewrite(original, rewritten) is ok


def test_wording_is_used_only_when_accepted():
    s = [Signal(code="first_contact", group="entity", verdict="unusual", weight="low", source="rules",
                message="Not in your vendor records or staff directory. New contacts happen, but check them first."),
         Signal(code="email_phone_mismatch", group="org", verdict="unusual", weight="medium", source="rules",
                message="Gives (206) 555-0177 to call, but Henry Schein's website lists (631) 843-5500")]
    r = AnalysisResult(message_id="x", intent=Intent.PAYMENT_REQUEST, decision=Decision.VERIFY_BEFORE_PAYING,
                       rule="unverified_company", signals=s, wording={0: "We have no record of this sender."})
    c = build_card(r, parse_eml(b"Message-ID: <x@a.com>\nFrom: a@b.com\n\nx"))
    assert "We have no record of this sender." in c.looks_unusual
    assert s[1].message in c.looks_unusual  # no rewrite given -> rule wording


def test_only_warnings_and_notes_are_sent_for_rewording(monkeypatch):
    from app.phase_a import card as card_mod
    sent = {}

    async def fake_complete_json(**kw):
        sent["lines"] = kw["messages"][1]["content"]
        return card_mod._WordingOut()
    monkeypatch.setattr(card_mod, "complete_json", fake_complete_json)
    s = [Signal(code="first_contact", group="entity", verdict="unusual", weight="low", source="r", message="WARN LINE"),
         Signal(code="known_sender", group="entity", verdict="fine", source="r", message="FINE LINE")]
    asyncio.run(card_mod.word_signals(s, "k"))
    assert "WARN LINE" in sent["lines"] and "FINE LINE" not in sent["lines"]
