"""Mail-client integration API (/api/v1): used by the Gmail Apps Script today, any provider later."""
import base64
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.clients import rdap, tavily_client
from app.main import app

ROOT = Path(__file__).parent.parent
A = {"X-BEC-Key": "key-riverbend"}
B = {"X-BEC-Key": "key-other"}


def raw(name: str) -> str:
    return base64.urlsafe_b64encode((ROOT / "scenarios" / name).read_bytes()).decode().rstrip("=")


def body(mid: str, scenario: str, **kw):
    return {"provider": "gmail", "mailbox": "ap@riverbend.test", "message_id": mid, "raw": raw(scenario), **kw}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("BEC_API_KEYS", "riverbend:key-riverbend,other:key-other")
    rdap._cache.clear()
    tavily_client._cache.clear()
    jobs.store.clear()
    with TestClient(app) as c:
        yield c


def wait_done(c, mid, headers=A, mailbox="ap@riverbend.test"):
    for _ in range(100):
        r = c.get(f"/api/v1/messages/gmail/{mid}", params={"mailbox": mailbox}, headers=headers)
        if r.status_code == 200 and r.json()["status"] in ("done", "error"):
            return r.json()
        time.sleep(0.03)
    raise AssertionError(f"{mid} never finished: {r.json()}")


# ---------- auth ----------

def test_not_configured_is_503(client, monkeypatch):
    monkeypatch.delenv("BEC_API_KEYS")
    assert client.post("/api/v1/messages", json=body("m1", "06_legit_invoice_control.eml"), headers=A).status_code == 503


@pytest.mark.parametrize("headers", [{}, {"X-BEC-Key": "wrong"}])
def test_missing_or_wrong_key_is_401(client, headers):
    assert client.post("/api/v1/messages", json=body("m1", "06_legit_invoice_control.eml"), headers=headers).status_code == 401


# ---------- ingest -> queued -> done ----------

def test_ingest_returns_202_then_analysis_completes(client):
    # Sample-inbox email -> sample-profile tenant (in the live profile "Sam Ortiz" is on file at another address).
    r = client.post("/api/v1/messages", json=body("m-bank", "02_hacked_vendor_thread.eml"), headers=B)
    assert r.status_code == 202 and r.json()["status"] in ("queued", "processing", "done")
    done = wait_done(client, "m-bank", headers=B)
    assert done["status"] == "done" and done["label"] == "verify"
    assert done["card"]["action"].startswith("Before paying, confirm the new bank details with")


def test_clean_email_gets_no_label(client):
    # Sample-inbox email -> tenant "other", which has no data folder and so uses the sample records it was written for.
    client.post("/api/v1/messages", json=body("m-ok", "06_legit_invoice_control.eml"), headers=B)
    assert wait_done(client, "m-ok", headers=B)["label"] == "none"


def test_duplicate_submit_is_not_reanalyzed(client, monkeypatch):
    calls = []
    real = jobs.analyze

    async def counting(e):
        calls.append(e.message_id)
        return await real(e)
    monkeypatch.setattr(jobs, "analyze", counting)
    first = client.post("/api/v1/messages", json=body("m-dup", "06_legit_invoice_control.eml"), headers=A)
    wait_done(client, "m-dup")
    again = client.post("/api/v1/messages", json=body("m-dup", "06_legit_invoice_control.eml"), headers=A)
    assert first.status_code == 202 and again.status_code == 200 and again.json()["status"] == "done"
    assert len(calls) == 1


def test_batch_status_for_the_scanner(client):
    client.post("/api/v1/messages", json=body("m-a", "02_hacked_vendor_thread.eml"), headers=A)
    wait_done(client, "m-a")
    r = client.post("/api/v1/messages/status", headers=A,
                    json={"provider": "gmail", "mailbox": "ap@riverbend.test", "ids": ["m-a", "never-sent"]})
    res = r.json()["results"]
    assert res["m-a"]["status"] == "done" and res["m-a"]["label"] == "verify" and res["m-a"]["headline"]
    assert res["never-sent"]["status"] == "unknown"


def test_recent_list_for_dashboard(client):
    client.post("/api/v1/messages", json=body("m-l", "03_fake_ceo_gift_cards.eml", folder="spam"), headers=A)
    wait_done(client, "m-l")
    items = client.get("/api/v1/messages", headers=A).json()["items"]
    assert items[0]["message_id"] == "m-l" and items[0]["subject"] == "Quick favor"
    assert items[0]["folder"] == "spam" and items[0]["decision"] == "VERIFY_BEFORE_PAYING"


def test_analysis_error_is_reported_without_internals(client, monkeypatch):
    async def boom(e):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(jobs, "analyze", boom)
    client.post("/api/v1/messages", json=body("m-err", "06_legit_invoice_control.eml"), headers=A)
    done = wait_done(client, "m-err")
    assert done["status"] == "error" and "secret" not in json.dumps(done)


# ---------- tenant isolation ----------

def test_other_tenant_cannot_see_results(client):
    client.post("/api/v1/messages", json=body("m-iso", "02_hacked_vendor_thread.eml"), headers=A)
    wait_done(client, "m-iso")
    assert client.get("/api/v1/messages/gmail/m-iso", params={"mailbox": "ap@riverbend.test"}, headers=B).status_code == 404
    assert client.get("/api/v1/messages", headers=B).json()["items"] == []
    st = client.post("/api/v1/messages/status", headers=B,
                     json={"provider": "gmail", "mailbox": "ap@riverbend.test", "ids": ["m-iso"]}).json()
    assert st["results"]["m-iso"]["status"] == "unknown"


# ---------- input validation ----------

def test_invalid_base64_is_400(client):
    r = client.post("/api/v1/messages", headers=A, json={**body("m-x", "06_legit_invoice_control.eml"), "raw": "%%%not-base64%%%"})
    assert r.status_code == 400


def test_email_without_sender_is_400(client):
    r = client.post("/api/v1/messages", headers=A,
                    json={**body("m-x", "06_legit_invoice_control.eml"), "raw": base64.urlsafe_b64encode(b"hello").decode()})
    assert r.status_code == 400


def test_too_large_is_413(client):
    big = "A" * (jobs.MAX_RAW_B64 + 4)
    r = client.post("/api/v1/messages", headers=A, json={**body("m-x", "06_legit_invoice_control.eml"), "raw": big})
    assert r.status_code == 413


@pytest.mark.parametrize("mid", ["", "has space", "x" * 300, "../etc"])
def test_bad_message_id_is_422(client, mid):
    assert client.post("/api/v1/messages", headers=A, json=body(mid, "06_legit_invoice_control.eml")).status_code == 422


# ---------- mailbox settings (rules / forwarding) ----------

def test_gmail_settings_report(client):
    fx = ROOT / "fixtures" / "mailbox"
    payload = {"provider": "gmail", "mailbox": "ap@riverbend.test",
               "filters": json.loads((fx / "gmail_filters.json").read_text()),
               "forwarding": json.loads((fx / "gmail_forwarding.json").read_text()),
               "auto_forwarding": json.loads((fx / "gmail_autoforwarding.json").read_text())}
    r = client.post("/api/v1/mailbox-settings", headers=A, json=payload)
    assert r.status_code == 200
    rep = r.json()
    assert rep["source"] == "live" and any(f["severity"] == "high" for f in rep["findings"])


def test_outlook_settings_report_shape_is_supported(client):
    fx = ROOT / "fixtures" / "mailbox"
    folders = {f["id"]: f["displayName"] for f in json.loads((fx / "outlook_folders.json").read_text())["value"]}
    payload = {"provider": "outlook", "mailbox": "ap@riverbend.test",
               "rules": json.loads((fx / "outlook_rules.json").read_text()), "folders": folders}
    rep = client.post("/api/v1/mailbox-settings", headers=A, json=payload).json()
    assert any("RSS Feeds" in r for f in rep["findings"] for r in f["reasons"])


# ---------- live tenant profile ----------

def _eml(sender, name, body, mid):
    raw = (f"Message-ID: <{mid}@yahoo.com>\nFrom: {name} <{sender}>\nTo: testorganization26@gmail.com\n"
           f"Subject: Invoice ACM-10437\nAuthentication-Results: mx.google.com; spf=pass; dkim=pass; dmarc=pass\n\n{body}")
    return base64.urlsafe_b64encode(raw.encode()).decode()


def test_live_tenant_uses_its_own_vendor_records(client):
    body_txt = ("Hi, please use our new account for ACM-10437 ($18,400.00).\nBank: Pacific Crest Bank\n"
                "Routing: 999000222\nAccount: 000058127731\nThanks, Sam")
    req = {"provider": "gmail", "mailbox": "testorganization26@gmail.com", "message_id": "live-1",
           "raw": _eml("test.vendor26@yahoo.com", "Sam Ortiz", body_txt, "live-1")}
    client.post("/api/v1/messages", json=req, headers=A)
    done = wait_done(client, "live-1", mailbox="testorganization26@gmail.com")
    assert done["label"] == "verify"
    card = done["card"]
    assert card["action"].startswith("Before paying, confirm the new bank details with")
    assert card["callback"]["phone"] == "(503) 555-0142" and card["callback"]["from"] == "your vendor records"
    assert not any("free email" in line for line in card["looks_unusual"])  # vendor on Yahoo is on file


def test_live_tenant_catches_vendor_username_on_another_provider(client):
    req = {"provider": "gmail", "mailbox": "testorganization26@gmail.com", "message_id": "live-2",
           "raw": _eml("test.vendor26@outlook.com", "Sam Ortiz", "Please pay ACM-10437 today. Thanks, Sam", "live-2")}
    client.post("/api/v1/messages", json=req, headers=A)
    done = wait_done(client, "live-2", mailbox="testorganization26@gmail.com")
    assert done["label"] == "verify"
    assert "test.vendor26@yahoo.com" in done["card"]["action"] or any(
        "test.vendor26@yahoo.com" in line for line in done["card"]["looks_unusual"])


# ---------- demo history (seeded by the add-on's seedDemoHistory) ----------

def test_demo_history_for_live_tenant(client):
    r = client.get("/api/v1/demo/history", headers=A)
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert len(msgs) >= 20 and all({"key", "labels", "raw"} <= set(m) for m in msgs)


def test_demo_history_not_available_for_other_tenants_or_without_key(client):
    assert client.get("/api/v1/demo/history", headers=B).status_code == 404
    assert client.get("/api/v1/demo/history").status_code == 401
