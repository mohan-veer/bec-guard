import asyncio

from app.phase_a.intent import classify_intent
from app.phase_a.models import Intent
from tests.helpers import load_scenario


def test_mock_intent_by_message_id(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    assert asyncio.run(classify_intent(load_scenario("03_fake_ceo_gift_cards.eml"))).intent == Intent.GIFT_CARDS
    assert asyncio.run(classify_intent(load_scenario("02_hacked_vendor_thread.eml"))).intent == Intent.BANK_CHANGE


def test_mock_intent_default_for_unknown_email(monkeypatch):
    from app.phase_a.parse import parse_eml
    monkeypatch.setenv("MOCK_MODE", "true")
    e = parse_eml(b"Message-ID: <never-seen@x.com>\nFrom: a@x.com\n\nhello")
    assert asyncio.run(classify_intent(e)).intent == Intent.PAYMENT_REQUEST


def test_gate0_returns_claimed_company(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    g = asyncio.run(classify_intent(load_scenario("05_fake_supplier_copied_name.eml")))
    assert g.claimed_company == "Harbor Medical Supply"
