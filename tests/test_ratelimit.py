import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import jobs, ratelimit
from app.main import app

ROOT = Path(__file__).parent.parent


def test_sliding_window_unit():
    w = ratelimit.SlidingWindow()
    assert [w.hit("k", limit=2, window=60, now=t) for t in (0, 1)] == [None, None]
    retry = w.hit("k", limit=2, window=60, now=2)
    assert retry == pytest.approx(58)          # oldest hit leaves the window at t=60
    assert w.hit("other", limit=2, window=60, now=2) is None
    assert w.hit("k", limit=2, window=60, now=61) is None


def test_client_ip_prefers_cloudflare_then_forwarded_header():
    class R:
        def __init__(self, headers): self.headers, self.client = headers, type("C", (), {"host": "127.0.0.1"})()
    assert ratelimit.client_ip(R({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "9.9.9.9"})) == "1.2.3.4"
    assert ratelimit.client_ip(R({"x-forwarded-for": "5.6.7.8, 10.0.0.1"})) == "5.6.7.8"
    assert ratelimit.client_ip(R({})) == "127.0.0.1"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("BEC_API_KEYS", "riverbend:key-riverbend")
    jobs.store.clear()
    with TestClient(app) as c:
        yield c


def test_public_check_is_limited_per_ip(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PUBLIC_PER_MINUTE", "2")
    ip_a, ip_b = {"cf-connecting-ip": "1.1.1.1"}, {"cf-connecting-ip": "2.2.2.2"}
    for _ in range(2):
        assert client.post("/api/scenarios/06_legit_invoice_control/check", headers=ip_a).status_code == 200
    r = client.post("/api/scenarios/06_legit_invoice_control/check", headers=ip_a)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert "detail" in r.json()
    assert client.post("/api/scenarios/06_legit_invoice_control/check", headers=ip_b).status_code == 200
    assert client.post("/api/mailbox/gmail/check", headers=ip_a).status_code == 429  # same budget for all public checks


def test_public_daily_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PUBLIC_PER_DAY", "1")
    h = {"cf-connecting-ip": "3.3.3.3"}
    assert client.post("/api/scenarios/06_legit_invoice_control/check", headers=h).status_code == 200
    assert client.post("/api/scenarios/06_legit_invoice_control/check", headers=h).status_code == 429


def _ingest(client, mid):
    raw = base64.urlsafe_b64encode((ROOT / "scenarios/06_legit_invoice_control.eml").read_bytes()).decode()
    return client.post("/api/v1/messages", headers={"X-BEC-Key": "key-riverbend"},
                       json={"provider": "gmail", "mailbox": "ap@riverbend.test", "message_id": mid, "raw": raw})


def test_ingest_limited_per_tenant_but_duplicates_are_free(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_INGEST_PER_MINUTE", "2")
    assert _ingest(client, "a").status_code == 202
    assert _ingest(client, "b").status_code == 202
    assert _ingest(client, "a").status_code == 200   # already known: not counted, not refused
    assert _ingest(client, "c").status_code == 429


def test_global_daily_analysis_budget(client, monkeypatch):
    monkeypatch.setenv("DAILY_ANALYSIS_BUDGET", "2")
    assert _ingest(client, "x1").status_code == 202
    assert client.post("/api/scenarios/06_legit_invoice_control/check", headers={"cf-connecting-ip": "4.4.4.4"}).status_code == 200
    r = _ingest(client, "x2")
    assert r.status_code == 429 and "daily" in r.json()["detail"].lower()
