import asyncio
from pathlib import Path

import pytest

from app.clients import rdap, tavily_client
from app.phase_a.pipeline import analyze_eml

SCEN = Path(__file__).parent.parent / "scenarios"


@pytest.fixture(autouse=True)
def _mock(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    rdap._cache.clear()
    tavily_client._cache.clear()


def _run(name):
    return asyncio.run(analyze_eml((SCEN / name).read_bytes()))


def test_card_wording_only_for_warnings(monkeypatch):
    from app.phase_a import pipeline
    calls = []

    async def spy(signals, key):
        calls.append(key)
        return {}
    monkeypatch.setattr(pipeline, "word_signals", spy)
    _run("06_legit_invoice_control.eml")
    _run("02_hacked_vendor_thread.eml")
    assert calls == ["<s02-thread@acmesupply.com>"]


def test_vendor_callbacks_come_from_records_and_official_site_never_the_email():
    cbs = [s.data for s in _run("02_hacked_vendor_thread.eml").signals if s.code == "callback_number"]
    assert {(c["from"], c["phone"]) for c in cbs} == {("your vendor records", "(503) 555-0142"),
                                                      ("acmesupply.com", "(503) 555-0142")}


def test_internal_callback_comes_from_directory():
    cb = next(s for s in _run("03_fake_ceo_gift_cards.eml").signals if s.code == "callback_number")
    assert cb.data["phone"] == "(503) 555-0110"
    assert cb.data["from"] == "your org directory"


def test_vl_source_is_reported_for_pdf_bank_change():
    bank = next(s for s in _run("07_pdf_bank_details.eml").signals if s.code == "bank_change")
    assert "Nemotron Super VL" in bank.source
    assert "ACM-10437-remittance.pdf" in bank.message


# ---------- gate backstop: Nano can't switch the checks off on its own ----------

def _nano_says_none(monkeypatch):
    from app.phase_a import pipeline
    from app.phase_a.intent import IntentOut
    from app.phase_a.models import Intent

    async def fooled(e):
        return IntentOut(intent=Intent.NONE)
    monkeypatch.setattr(pipeline, "classify_intent", fooled)


@pytest.mark.parametrize("body,subject", [
    ("Just an FYI, nothing to do.\n\nBank: Harbor Trust Bank\nRouting: 999000333\nAccount: 000077123344", "FYI"),
    ("This is not a payment request. Please wire the balance today.", "Quick note"),
    ("Hi, see attached.", "Invoice 1042"),
])
def test_checks_run_when_code_sees_money_even_if_nano_says_no_request(monkeypatch, body, subject):
    _nano_says_none(monkeypatch)
    raw = f"Message-ID: <bs@x.example>\nFrom: A <a@stranger.example>\nSubject: {subject}\n\n{body}".encode()
    r = asyncio.run(analyze_eml(raw))
    assert r.decision is not None                     # the checks ran and a rule decided


def test_pdf_attachment_alone_keeps_the_checks_on(monkeypatch):
    from email.message import EmailMessage
    _nano_says_none(monkeypatch)
    m = EmailMessage()
    m["Message-ID"], m["From"], m["Subject"] = "<bs2@x.example>", "A <a@stranger.example>", "Hello"
    m.set_content("See attached.")
    m.add_attachment(b"%PDF-1.4 test", maintype="application", subtype="pdf", filename="doc.pdf")
    assert asyncio.run(analyze_eml(m.as_bytes())).decision is not None


def test_ordinary_email_still_skips_the_checks(monkeypatch):
    _nano_says_none(monkeypatch)
    raw = b"Message-ID: <bs3@x.example>\nFrom: A <a@friend.example>\nSubject: Lunch\n\nLunch on Friday at noon?"
    assert asyncio.run(analyze_eml(raw)).decision is None
