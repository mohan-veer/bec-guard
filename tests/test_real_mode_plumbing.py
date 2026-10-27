"""Real-mode plumbing: model clients per event loop; the sample inbox's fictional world keeps simulated web/domain facts."""
import asyncio
from datetime import date

import httpx
import pytest

from app.clients import llm, rdap, tavily_client
from app.phase_a import data


def test_llm_client_is_per_event_loop(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    llm._clients.clear()

    async def get_twice():
        return llm._client(), llm._client()
    a1, a2 = asyncio.run(get_twice())
    b1, _ = asyncio.run(get_twice())
    assert a1 is a2          # reused within one loop
    assert a1 is not b1      # a new loop gets its own client (an old loop's connections die with it)


@pytest.fixture(autouse=True)
def _clear():
    rdap._cache.clear()
    tavily_client._cache.clear()


def test_sample_profile_uses_simulated_rdap_even_in_real_mode(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setattr(rdap, "_http", lambda: pytest.fail("sample inbox must not query the real internet"))
    assert asyncio.run(rdap.registration_date("acmesupply.com")) == date(2009, 3, 17)


def test_live_tenant_uses_real_rdap(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(404)
    monkeypatch.setattr(rdap, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with data.using_profile("riverbend"):
        asyncio.run(rdap.registration_date("example.org"))
    assert calls == ["https://rdap.org/domain/example.org"]


def test_sample_profile_uses_simulated_tavily_even_with_a_key(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-x")
    monkeypatch.setattr(tavily_client, "_client", lambda: pytest.fail("sample inbox must not search the real web"))
    hits = asyncio.run(tavily_client.search("Acme Supply official website"))
    assert hits and hits[0].url.startswith("https://acmesupply.com")


def test_live_tenant_uses_real_tavily(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-x")
    seen = []

    async def search(**kw):
        seen.append(kw["query"])
        return {"results": []}
    monkeypatch.setattr(tavily_client, "_client", lambda: type("C", (), {"search": staticmethod(search)})())
    with data.using_profile("riverbend"):
        asyncio.run(tavily_client.search("Some Company official website"))
    assert seen == ["Some Company official website"]


@pytest.mark.parametrize("query", ["Harbor Medical Supply official site", "harbor medical supply website",
                                   "Harbor Medical Supply Inc official website"])
def test_simulated_search_matches_the_closest_saved_query(monkeypatch, query):
    monkeypatch.setenv("MOCK_MODE", "true")
    hits = asyncio.run(tavily_client.search(query))
    assert any("harbormedicalsupply.com" in h.url for h in hits)


def test_simulated_search_with_nothing_similar_is_empty(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    assert asyncio.run(tavily_client.search("weather in Lisbon tomorrow")) == []
