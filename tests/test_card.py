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


def test_bank_change_card_matches_brief_format():
    c = _card("02_hacked_vendor_thread.eml")
    assert c.headline == "Verify before paying"
    assert c.action == ("Bank details changed. Before paying, call Acme Supply at (503) 555-0142 "
                        "(number from acmesupply.com, not from this email) and confirm the new account.")
    assert "New bank account ending 7731 (previously 4821, used on 6 invoices)" == c.looks_unusual[0]  # strong first
    assert "Asks to switch from ACH to wire" in c.looks_unusual
    assert "Amount ($18,400.00) is within Acme Supply's usual range" in c.looks_fine


def test_lookalike_card_names_the_real_domain_and_keeps_original_case():
    c = _card("01_lookalike_vendor.eml")
    assert c.action.startswith("This email is not from acmesupply.com.")
    assert any("acmesuppIy.com looks like acmesupply.com" in line for line in c.looks_unusual)


def test_gift_card_and_internal_callback():
    c = _card("03_fake_ceo_gift_cards.eml")
    assert c.action.startswith("Gift card request.") or c.action.startswith("Dana Whitfield is writing")
    assert "(503) 555-0110 (number from your org directory, not from this email)" in c.action


def test_no_issues_card():
    c = _card("06_legit_invoice_control.eml")
    assert c.headline == "No issues found"
    assert c.looks_unusual == []
    assert c.explanation is None


def test_first_contact_line_is_shown():
    assert "First contact with this sender: no history to compare." in _card("05_fake_supplier_copied_name.eml").looks_unusual


def test_checks_panel_lists_every_check_with_its_source():
    c = _card("07_pdf_bank_details.eml")
    assert all(ch.source for ch in c.checks)
    assert any("Nemotron Super VL" in ch.source for ch in c.checks)
    assert any(ch.source == "Nemotron Nano" for ch in c.checks)


def test_no_callback_falls_back_to_number_on_file_wording():
    e = parse_eml(b"Message-ID: <x@a.com>\nFrom: A <a@unknown.com>\n\nPay now")
    r = AnalysisResult(message_id="x", intent=Intent.PAYMENT_REQUEST, decision=Decision.VERIFY_BEFORE_PAYING,
                       rule="any_strong_signal", signals=[])
    assert "a phone number you already have on file, not one from this email" in build_card(r, e).action


def test_no_request_card():
    e = parse_eml(b"Message-ID: <x@a.com>\nFrom: a@a.com\n\nLunch?")
    r = AnalysisResult(message_id="x", intent=Intent.NONE, decision=None, rule=None,
                       signals=[Signal(code="intent", group="gate", verdict="info", message="m", source="Nemotron Nano")])
    c = build_card(r, e)
    assert c.headline == "No money or data request found"
