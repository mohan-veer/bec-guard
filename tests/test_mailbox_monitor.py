"""Mailbox takeover signals for the org's own Gmail: settings that are NEW since the last check, and Google's own
security-alert emails (verified by DKIM/DMARC so a spoofed "Google" alert is ignored)."""
import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import account_events, jobs
from app.main import app

ROOT = Path(__file__).parent.parent
A = {"X-BEC-Key": "key-riverbend"}
MAILBOX = "testorganization26@gmail.com"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("BEC_API_KEYS", "riverbend:key-riverbend")
    jobs.store.clear()
    account_events.reset()
    with TestClient(app) as c:
        yield c


def _settings(filters):
    return {"provider": "gmail", "mailbox": MAILBOX, "filters": {"filter": filters}, "forwarding": {},
            "auto_forwarding": {}}


HACKER_FILTER = {"id": "f-evil", "criteria": {"query": "invoice OR payment OR bank"},
                 "action": {"removeLabelIds": ["INBOX", "UNREAD"]}}
NEWSLETTER = {"id": "f-news", "criteria": {"from": "news@x.com"}, "action": {"addLabelIds": ["Label_1"]}}


def test_first_check_sets_the_baseline_then_new_rules_are_flagged(client):
    first = client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER]), headers=A).json()
    assert first["changes"] == {"first_check": True, "new": []}
    second = client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER, HACKER_FILTER]), headers=A).json()
    assert second["changes"]["first_check"] is False
    assert second["changes"]["new"] == ["rule:f-evil"]
    f = next(x for x in second["findings"] if x["id"] == "rule:f-evil")
    assert f["new_since_last_check"] is True and f["severity"] == "high"


def test_unchanged_settings_report_no_changes(client):
    client.post("/api/v1/mailbox-settings", json=_settings([HACKER_FILTER]), headers=A)
    again = client.post("/api/v1/mailbox-settings", json=_settings([HACKER_FILTER]), headers=A).json()
    assert again["changes"]["new"] == []


def _alert(sender, dkim_domain, subject, mid, auth="pass"):
    raw = (f"Message-ID: <{mid}@x>\nFrom: Google <{sender}>\nTo: {MAILBOX}\nSubject: {subject}\n"
           f"Authentication-Results: mx.google.com; spf={auth}; dkim={auth} header.d={dkim_domain}; dmarc={auth}\n\n"
           "We noticed a new sign-in to your Google Account on a Windows device.")
    return {"provider": "gmail", "mailbox": MAILBOX, "message_id": mid,
            "raw": base64.urlsafe_b64encode(raw.encode()).decode()}


def test_verified_google_security_alert_is_recorded(client):
    client.post("/api/v1/messages", json=_alert("no-reply@accounts.google.com", "accounts.google.com",
                                                "Security alert", "g1"), headers=A)
    ev = client.get("/api/v1/account-events", headers=A).json()["events"]
    assert len(ev) == 1 and ev[0]["kind"] == "google_security_alert" and ev[0]["subject"] == "Security alert"
    assert ev[0]["mailbox"] == MAILBOX


def test_spoofed_google_alert_is_ignored(client):
    client.post("/api/v1/messages", json=_alert("no-reply@accounts.google.com", "evil.example", "Security alert",
                                                "g2", auth="fail"), headers=A)
    assert client.get("/api/v1/account-events", headers=A).json()["events"] == []


def test_ordinary_google_mail_is_not_an_account_alert(client):
    client.post("/api/v1/messages", json=_alert("no-reply@accounts.google.com", "accounts.google.com",
                                                "Welcome to your new Google Account", "g3"), headers=A)
    assert client.get("/api/v1/account-events", headers=A).json()["events"] == []
