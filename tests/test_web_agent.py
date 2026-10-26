"""Web agent: guardrails (pure), the tool loop (scripted model), the 6-search cap, and the fixed-step fallback."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.clients import llm, tavily_client
from app.clients.tavily_client import SearchHit
from app.phase_a import web_agent
from app.phase_a.web_agent import AgentAnswer, validate

HITS = [
    SearchHit(url="https://harbormedicalsupply.com/", content="Distributor since 2004."),
    SearchHit(url="https://www.harbormedicalsupply.com/contact", content="Billing: (206) 555-0198."),
    SearchHit(url="https://scam-reviews.example/harbor", content="Harbor Medical Supply phone (206) 555-0111"),
]


@pytest.fixture(autouse=True)
def _clear():
    tavily_client._cache.clear()


# ---------- guardrails ----------

def test_valid_answer_is_accepted_and_pages_counted():
    f = validate(AgentAnswer(official_domain="harbormedicalsupply.com", phone="206-555-0198"), HITS, "email body")
    assert f.official_domain == "harbormedicalsupply.com"
    assert f.phone == "(206) 555-0198"
    assert f.phone_url == "https://www.harbormedicalsupply.com/contact"
    assert f.pages == 2


def test_domain_not_in_returned_urls_is_rejected():
    f = validate(AgentAnswer(official_domain="harbor-invented.com", phone="(206) 555-0198"), HITS, "")
    assert f.official_domain is None and f.phone is None


def test_url_given_as_domain_is_normalised():
    f = validate(AgentAnswer(official_domain="https://www.HarborMedicalSupply.com/about"), HITS, "")
    assert f.official_domain == "harbormedicalsupply.com"


def test_phone_from_third_party_page_is_rejected():
    f = validate(AgentAnswer(official_domain="harbormedicalsupply.com", phone="(206) 555-0111"), HITS, "")
    assert f.official_domain == "harbormedicalsupply.com" and f.phone is None


def test_phone_that_appears_in_the_email_is_rejected():
    f = validate(AgentAnswer(official_domain="harbormedicalsupply.com", phone="(206) 555-0198"), HITS,
                 "Call me at 206.555.0198 to confirm")
    assert f.phone is None


def test_invented_phone_not_on_any_page_is_rejected():
    f = validate(AgentAnswer(official_domain="harbormedicalsupply.com", phone="(206) 555-0000"), HITS, "")
    assert f.phone is None


# ---------- agent loop (mock script) ----------

def test_mock_agent_runs_scripted_tool_calls_through_real_tavily_mock(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    f = asyncio.run(web_agent.find_official_contact("Harbor Medical Supply", "<s05-newvendor@harbormedsupply.co>", ""))
    assert f.method == "agent"
    assert f.searches == 2
    assert f.official_domain == "harbormedicalsupply.com"
    assert f.phone == "(206) 555-0198"


# ---------- real-mode loop with a fake client ----------

def _tool_call_reply(i):
    tc = SimpleNamespace(id=f"c{i}", type="function",
                         function=SimpleNamespace(name="web_search", arguments=json.dumps({"query": f"q{i}"})))
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tc]))], usage=None)


def _final_reply(obj):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(obj), tool_calls=None))],
                           usage=None)


def _install(monkeypatch, replies):
    calls = []

    async def create(**kw):
        calls.append(kw)
        return replies(len(calls), kw)
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    searched = []

    async def fake_search(query, include_domains=None, max_results=5):
        searched.append(query)
        return HITS
    monkeypatch.setattr(web_agent, "search", fake_search)
    return calls, searched


def test_search_cap_is_six_then_final_answer_is_forced(monkeypatch):
    def replies(n, kw):
        if "tools" not in kw:  # forced final turn has no tools
            return _final_reply({"official_domain": "harbormedicalsupply.com", "phone": None})
        return _tool_call_reply(n)
    calls, searched = _install(monkeypatch, replies)
    f = asyncio.run(web_agent.find_official_contact("Harbor Medical Supply", "k", ""))
    assert len(searched) == 6
    assert f.searches == 6 and f.method == "agent"
    assert f.official_domain == "harbormedicalsupply.com"
    assert "tools" not in calls[-1]


def test_model_without_tool_calls_and_bad_json_falls_back_to_fixed_steps(monkeypatch):
    def replies(n, kw):
        if kw.get("tools"):
            return _final_reply_text("I cannot use tools")
        return _final_reply({"official_domain": "harbormedicalsupply.com"})  # fixed-step domain pick
    calls, searched = _install(monkeypatch, replies)
    f = asyncio.run(web_agent.find_official_contact("Harbor Medical Supply", "k", ""))
    assert f.method == "fixed"
    assert f.official_domain == "harbormedicalsupply.com"
    assert f.phone == "(206) 555-0198"  # phone found by regex on the official domain's pages
    assert searched[0] == "Harbor Medical Supply official website"


def _final_reply_text(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))], usage=None)
