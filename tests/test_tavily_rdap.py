import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.clients import rdap, tavily_client
from app.phase_a import data


@pytest.fixture(autouse=True)
def _clear_caches():
    rdap._cache.clear()
    tavily_client._cache.clear()


@pytest.fixture
def live_tenant():
    # Real lookups only happen for live tenants; the sample inbox's fictional world always stays simulated.
    with data.using_profile("riverbend"):
        yield


# ---------- Tavily ----------

def test_tavily_mock_returns_fixture(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    hits = asyncio.run(tavily_client.search("Harbor Medical Supply official website"))
    assert hits and hits[0].url.startswith("https://")


def test_tavily_mock_unknown_query_is_empty(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    assert asyncio.run(tavily_client.search("never seen query")) == []


def _fake_tavily(monkeypatch, response):
    calls = []

    async def search(**kw):
        calls.append(kw)
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    monkeypatch.setattr(tavily_client, "_client", lambda: SimpleNamespace(search=search))
    return calls


def test_tavily_real_passes_params_and_caches(monkeypatch, live_tenant):
    calls = _fake_tavily(monkeypatch, {"results": [{"title": "T", "url": "https://a.com", "content": "c", "score": 0.9}]})
    for _ in range(2):
        hits = asyncio.run(tavily_client.search("acme phone", include_domains=["a.com"]))
    assert hits[0].url == "https://a.com"
    assert len(calls) == 1  # second call served from cache
    assert calls[0]["search_depth"] == "basic"
    assert calls[0]["include_domains"] == ["a.com"]


def test_tavily_error_returns_empty(monkeypatch, live_tenant):
    _fake_tavily(monkeypatch, RuntimeError("quota"))
    assert asyncio.run(tavily_client.search("x")) == []


# ---------- RDAP ----------

def test_rdap_mock_fixture(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    assert asyncio.run(rdap.registration_date("harbormedsupply.co")) == date.today() - timedelta(days=17)
    assert asyncio.run(rdap.registration_date("acmesupply.com")) == date(2009, 3, 17)
    assert asyncio.run(rdap.registration_date("unknown-domain.com")) is None


def _fake_rdap(monkeypatch, handler):
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setattr(rdap, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_rdap_real_reads_registration_event_and_caches(monkeypatch, live_tenant):
    hits = []

    def handler(req):
        hits.append(str(req.url))
        return httpx.Response(200, json={"events": [{"eventAction": "expiration", "eventDate": "2030-01-01T00:00:00Z"},
                                                    {"eventAction": "registration", "eventDate": "1999-05-04T12:00:00Z"}]})
    _fake_rdap(monkeypatch, handler)
    for _ in range(2):
        assert asyncio.run(rdap.registration_date("Example.com")) == date(1999, 5, 4)
    assert hits == ["https://rdap.org/domain/example.com"]


def test_rdap_404_and_errors_are_none(monkeypatch, live_tenant):
    _fake_rdap(monkeypatch, lambda req: httpx.Response(404))
    assert asyncio.run(rdap.registration_date("nope.com")) is None

    def boom(req):
        raise httpx.ConnectError("down")
    _fake_rdap(monkeypatch, boom)
    assert asyncio.run(rdap.registration_date("down.com")) is None
