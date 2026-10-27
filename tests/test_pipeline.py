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
