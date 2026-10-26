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


def test_explanation_only_when_not_fine():
    assert _run("06_legit_invoice_control.eml").explanation is None
    assert _run("02_hacked_vendor_thread.eml").explanation


def test_vendor_callback_comes_from_official_site_not_email():
    cb = next(s for s in _run("02_hacked_vendor_thread.eml").signals if s.code == "callback_number")
    assert cb.data["phone"] == "(503) 555-0142"
    assert cb.data["from"] == "acmesupply.com"


def test_internal_callback_comes_from_directory():
    cb = next(s for s in _run("03_fake_ceo_gift_cards.eml").signals if s.code == "callback_number")
    assert cb.data["phone"] == "(503) 555-0110"
    assert cb.data["from"] == "your org directory"


def test_vl_source_is_reported_for_pdf_bank_change():
    bank = next(s for s in _run("07_pdf_bank_details.eml").signals if s.code == "bank_change")
    assert "Nemotron Super VL" in bank.source
    assert "ACM-10437-remittance.pdf" in bank.message
