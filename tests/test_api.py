import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clients import rdap, tavily_client
from app.main import MAX_UPLOAD_BYTES, app

SCEN = Path(__file__).parent.parent / "scenarios"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    rdap._cache.clear()
    tavily_client._cache.clear()
    with TestClient(app) as c:
        yield c


def _events(resp):
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_list_scenarios(client):
    items = client.get("/api/scenarios").json()
    assert len(items) == 7
    first = items[0]
    assert first["id"] == "01_lookalike_vendor"
    assert first["from_addr"] == "ar@acmesuppIy.com"  # original case for display
    assert first["title"] == "Lookalike vendor domain"


def test_get_scenario_email(client):
    e = client.get("/api/scenarios/07_pdf_bank_details").json()
    assert e["subject"] == "Re: Invoice ACM-10437"
    assert e["attachments"] == [{"filename": "ACM-10437-remittance.pdf", "content_type": "application/pdf", "size": 906}]


@pytest.mark.parametrize("bad", ["nope", "..%2F..%2Fapp%2Fmain", "01_lookalike_vendor.eml"])
def test_unknown_scenario_is_404(client, bad):
    assert client.get(f"/api/scenarios/{bad}").status_code == 404
    # An encoded "/" doesn't match the API route and falls through to the static UI mount (405 for POST).
    assert client.post(f"/api/scenarios/{bad}/check").status_code in (404, 405)


@pytest.mark.parametrize("path", ["/..%2Fapp%2Fmain.py", "/../app/main.py", "/%2e%2e/.env.example"])
def test_static_ui_never_serves_files_outside_dist(client, path):
    r = client.get(path)
    assert "FastAPI" not in r.text and "NEBIUS_API_KEY" not in r.text


def test_check_stream_order_and_early_warning(client, monkeypatch):
    # Mock checks finish instantly; make the slow org group (web agent, RDAP) actually slow, as in real mode.
    import asyncio
    from app.phase_a import pipeline
    real_run_org = pipeline.run_org

    async def slow_run_org(e, gate):
        await asyncio.sleep(0.05)
        return await real_run_org(e, gate)
    monkeypatch.setattr(pipeline, "run_org", slow_run_org)

    ev = _events(client.post("/api/scenarios/01_lookalike_vendor/check"))
    types = [e["type"] for e in ev]
    assert types[0] == "email" and types[1] == "gate" and types[-1] == "result"
    assert "early" in types and types.index("early") < types.index("result")
    assert ev[-1]["card"]["decision"] == "VERIFY_BEFORE_PAYING"
    groups = {e["group"] for e in ev if e["type"] == "signals"}
    assert groups == {"entity", "org", "content"}


def test_no_early_warning_for_clean_email(client):
    ev = _events(client.post("/api/scenarios/06_legit_invoice_control/check"))
    assert "early" not in [e["type"] for e in ev]
    assert ev[-1]["card"]["decision"] == "NO_ISSUES_FOUND"


def test_upload_raw_eml(client):
    raw = (SCEN / "02_hacked_vendor_thread.eml").read_bytes()
    ev = _events(client.post("/api/check", content=raw, headers={"content-type": "message/rfc822"}))
    assert ev[0]["email"]["from_addr"] == "ar@acmesupply.com"
    assert ev[-1]["card"]["decision"] == "VERIFY_BEFORE_PAYING"


def test_upload_too_large_is_413(client):
    r = client.post("/api/check", content=b"x" * (MAX_UPLOAD_BYTES + 1))
    assert r.status_code == 413


@pytest.mark.parametrize("body", [b"", b"just some text without headers"])
def test_upload_without_sender_is_400(client, body):
    r = client.post("/api/check", content=body)
    assert r.status_code == 400
    assert "detail" in r.json() and "Traceback" not in r.text


def test_internal_error_is_reported_in_stream_without_internals(client, monkeypatch):
    from app import main

    async def boom(e):
        raise RuntimeError("secret internal detail")
        yield  # pragma: no cover
    monkeypatch.setattr(main, "analyze_events", boom)
    ev = _events(client.post("/api/scenarios/06_legit_invoice_control/check"))
    assert ev[-1]["type"] == "error"
    assert "secret" not in json.dumps(ev)


def test_early_warning_always_has_a_reason(client):
    # Scenario 2: Gate 0 says bank_change, so VERIFY is known before any strong signal exists.
    for sid in ["02_hacked_vendor_thread", "07_pdf_bank_details", "03_fake_ceo_gift_cards"]:
        early = [e for e in _events(client.post(f"/api/scenarios/{sid}/check")) if e["type"] == "early"]
        for e in early:
            assert e["reason"].strip(), sid


@pytest.mark.parametrize("provider", ["outlook", "gmail"])
def test_mailbox_check_fixture(client, provider):
    r = client.post(f"/api/mailbox/{provider}/check")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fixture"
    highs = [f for f in body["findings"] if f["severity"] == "high"]
    assert highs and all(f["next_step"] for f in body["findings"])
    assert all(f["explanation"] for f in highs)  # one-line Nemotron explanation (mock)
    assert any("Entra ID P1" in lim for lim in body["limits"])


def test_mailbox_unknown_provider_404(client):
    assert client.post("/api/mailbox/yahoo/check").status_code == 404
