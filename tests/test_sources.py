"""Source links: the web pages that actually supported a conclusion are shown under the line they support."""
import asyncio

import pytest

from app.phase_a import org
from app.phase_a.card import build_card
from app.phase_a.models import AnalysisResult, Decision, Intent
from app.phase_a.parse import parse_eml
from app.phase_a.web_agent import WebFinding


def _finding(simulated=False):
    return WebFinding(official_domain="henryschein.com", phone="(631) 843-5500",
                      phone_url="https://www.henryschein.com/us-en/contact", official_url="https://www.henryschein.com/",
                      official_title="Henry Schein Dental", phone_title="Contact Henry Schein", pages=2, searches=2,
                      simulated=simulated)


def _signals(monkeypatch, finding, body="Call me at (206) 555-0177"):
    async def fake(company, key, text):
        return finding
    monkeypatch.setattr(org, "find_official_contact", fake)
    sigs = asyncio.run(org.check_web_consensus("Henry Schein", "outlook.com", "k", body, None))
    sigs += org.check_email_phones(body, [s for s in sigs if s.code == "callback_number"])
    return {s.code: s for s in sigs}


def test_website_and_phone_lines_carry_the_pages_that_support_them(monkeypatch):
    s = _signals(monkeypatch, _finding())
    assert s["web_consensus_mismatch"].data["sources"] == [
        {"title": "Henry Schein Dental", "url": "https://www.henryschein.com/"}]
    assert s["email_phone_mismatch"].data["sources"] == [
        {"title": "Contact Henry Schein", "url": "https://www.henryschein.com/us-en/contact"}]


def test_simulated_web_results_never_get_links(monkeypatch):
    s = _signals(monkeypatch, _finding(simulated=True))
    assert "sources" not in s["web_consensus_mismatch"].data
    assert "sources" not in s["email_phone_mismatch"].data


def test_card_items_show_sources(monkeypatch):
    sigs = list(_signals(monkeypatch, _finding()).values())
    r = AnalysisResult(message_id="x", intent=Intent.PAYMENT_REQUEST, decision=Decision.VERIFY_BEFORE_PAYING,
                       rule="unverified_company", signals=sigs)
    card = build_card(r, parse_eml(b"Message-ID: <x@a>\nFrom: a@outlook.com\n\nx"))
    company = next(s for s in card.sections if s.title == "The company")
    assert company.items[0].sources == [{"title": "Henry Schein Dental", "url": "https://www.henryschein.com/"}]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://x.com/a", "", "not a url"])
def test_only_web_links_are_kept(monkeypatch, url):
    s = _signals(monkeypatch, _finding().model_copy(update={"official_url": url}))
    assert "sources" not in s["web_consensus_mismatch"].data
