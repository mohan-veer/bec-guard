import asyncio

from app.phase_a.content import LanguageOut, StyleOut, check_language, check_style, extract_from_attachments, \
    language_signals, render_pages
from app.phase_a.data import load_ledger
from tests.helpers import load_scenario


def _codes(signals):
    return {s.code: s for s in signals}


def test_urgency_plus_secrecy_is_one_medium_signal():
    s = _codes(language_signals(LanguageOut(urgency=True, secrecy=True, quotes=["keep this between us"])))
    assert set(s) == {"urgency_secrecy"} and s["urgency_secrecy"].weight == "medium"
    assert "keep this between us" in s["urgency_secrecy"].message


def test_urgency_alone_is_low_with_quote():
    s = _codes(language_signals(LanguageOut(urgency=True, quotes=["Please process today"])))
    assert s["time_pressure"].weight == "low"
    assert s["time_pressure"].message == '"Please process today" adds time pressure'


def test_channel_switch_low_and_nothing_when_clean():
    assert _codes(language_signals(LanguageOut(channel_switch=True)))["channel_switch"].weight == "low"
    assert language_signals(LanguageOut()) == []


def test_mock_language_for_gift_card_email(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    s = _codes(asyncio.run(check_language(load_scenario("03_fake_ceo_gift_cards.eml"))))
    assert "urgency_secrecy" in s and s["urgency_secrecy"].source == "Nemotron Super"


def test_style_skipped_without_history(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    s = asyncio.run(check_style(load_scenario("05_fake_supplier_copied_name.eml"), None))
    assert s == []


def test_style_mismatch_is_low(monkeypatch):
    from app.phase_a.content import style_signals
    s = style_signals(StyleOut(mismatch=True, reason="much more formal than usual"))
    assert s[0].code == "style_mismatch" and s[0].weight == "low"


def test_render_pdf_pages_to_png():
    pdf = load_scenario("07_pdf_bank_details.eml").attachments[0]
    pages = render_pages(pdf)
    assert len(pages) == 1 and pages[0].startswith(b"\x89PNG")


def test_vl_extracts_bank_details_from_pdf_in_mock(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    d = asyncio.run(extract_from_attachments(load_scenario("07_pdf_bank_details.eml")))
    assert d.account_last4 == "7731" and d.method == "wire" and d.routing_number == "999000222"


def test_no_attachments_means_no_vl_call(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    assert asyncio.run(extract_from_attachments(load_scenario("02_hacked_vendor_thread.eml"))) is None
