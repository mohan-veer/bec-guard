"""Mailbox takeover: suspicious activity (sent / trashed / deleted), new settings, office hours, the mailbox banner,
"This was me", and the compliance notice (the agreed test cases 1-8)."""
import base64
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import account_events, jobs
from app.main import app
from app.phase_b import takeover

A = {"X-BEC-Key": "key-riverbend"}
MAILBOX = "testorganization26@gmail.com"
VENDOR = "test.vendor26@yahoo.com"
PT = ZoneInfo("America/Los_Angeles")
TUE_11AM = int(datetime(2026, 10, 27, 11, 0, tzinfo=PT).timestamp())
TUE_2AM = int(datetime(2026, 10, 27, 2, 7, tzinfo=PT).timestamp())
COMPLIANCE = {"office_hours": {"timezone": "America/Los_Angeles", "days": [0, 1, 2, 3, 4], "start": "08:00",
                               "end": "18:00"},
              "compliance_contacts": [{"name": "Compliance", "email": "compliance.test@gmail.com"}]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("BEC_API_KEYS", "riverbend:key-riverbend")
    jobs.store.clear()
    account_events.reset()
    clock = {"now": TUE_11AM}
    monkeypatch.setattr(takeover, "now", lambda: clock["now"])
    account_events.start_monitoring("riverbend", MAILBOX, TUE_11AM - 86400)  # watching since the day before
    from app.phase_b import mailbox_check
    monkeypatch.setattr(mailbox_check, "_explained", {})
    with TestClient(app) as c:
        c.clock = clock
        yield c


@pytest.fixture
def placeholder_contact(monkeypatch):
    s = {**COMPLIANCE, "compliance_contacts": [{"email": "compliance-placeholder@bec-guard.invalid"}]}
    monkeypatch.setattr(takeover, "security_settings", lambda: takeover.SecuritySettings.model_validate(s))


@pytest.fixture
def real_contact(monkeypatch):
    monkeypatch.setattr(takeover, "security_settings", lambda: takeover.SecuritySettings.model_validate(COMPLIANCE))


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _sent_raw(to: str, body: str, mid: str = "s1") -> str:
    return _b64(f"Message-ID: <{mid}@mail.gmail.com>\nFrom: Jordan Ellis <{MAILBOX}>\nTo: {to}\n"
                f"Subject: Re: Invoice ACM-10437\n\n{body}")


def _activity(events, baseline=False):
    return {"provider": "gmail", "mailbox": MAILBOX, "events": events, "baseline": baseline}


def _sent(mid, to, body, t=TUE_11AM):
    return {"kind": "sent", "message_id": mid, "message_time": t, "detected_at": t, "labels": ["SENT"],
            "from": MAILBOX, "to": [to], "subject": "Re: Invoice ACM-10437", "raw": _sent_raw(to, body, mid)}


def _removed(kind, mid, t_msg, t_seen, labels, sender="", subject=""):
    return {"kind": kind, "message_id": mid, "message_time": t_msg, "detected_at": t_seen, "labels": labels,
            "from": sender, "to": [], "subject": subject}


def _settings(filters, send_as=None):
    return {"provider": "gmail", "mailbox": MAILBOX, "filters": {"filter": filters}, "forwarding": {},
            "auto_forwarding": {}, "send_as": {"sendAs": send_as or [{"sendAsEmail": MAILBOX, "isPrimary": True}]}}


NEWSLETTER = {"id": "f-news", "criteria": {"from": "news@x.com"}, "action": {"addLabelIds": ["Label_1"]}}
HIDE_VENDOR = {"id": "f-vendor", "criteria": {"from": VENDOR}, "action": {"removeLabelIds": ["INBOX"]}}
MARK_READ = {"id": "f-read", "criteria": {"from": "someone@x.com"}, "action": {"removeLabelIds": ["UNREAD"]}}
BANK_BODY = "Hi Sam,\nPlease use this account.\nBank: Lakeshore Commerce Bank\nRouting: 999000666\nAccount: 000044019055\n"


# 1. new filter matching a vendor on file -> high, compliance emailed once
def test_filter_hiding_vendor_mail_is_high_and_notified_once(client, real_contact):
    client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER]), headers=A)  # baseline
    r = client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER, HIDE_VENDOR]), headers=A).json()
    f = next(x for x in r["findings"] if x["id"] == "rule:f-vendor")
    assert f["severity"] == "high" and any("Acme Supply" in reason for reason in f["reasons"])
    assert r["alerts"]["open"] == 1 and len(r["notify"]) == 1
    assert r["notify"][0]["to"] == ["compliance.test@gmail.com"] and MAILBOX in r["notify"][0]["subject"]
    again = client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER, HIDE_VENDOR]), headers=A).json()
    assert again["notify"] == [] and again["alerts"]["open"] == 1


def test_placeholder_contact_never_sends(client, placeholder_contact):
    client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER]), headers=A)
    r = client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER, HIDE_VENDOR]), headers=A).json()
    assert r["alerts"]["open"] == 1 and r["notify"] == []
    assert "compliance contact" in r["notify_skipped"].lower()


# 2. sent email deleted soon after sending -> high; deleted much later -> nothing
def test_sent_then_deleted_soon_is_high(client, real_contact):
    client.post("/api/v1/mailbox-activity", json=_activity([_sent("s1", VENDOR, "Hi Sam, thanks.")]), headers=A)
    r = client.post("/api/v1/mailbox-activity", headers=A, json=_activity(
        [_removed("deleted", "s1", TUE_11AM, TUE_11AM + 300, ["SENT"])])).json()
    assert [f["severity"] for f in r["findings"]] == ["high"]
    assert "deleted soon after sending" in r["findings"][0]["title"].lower()
    assert VENDOR in " ".join(r["findings"][0]["reasons"])  # who it went to, remembered from the sent event
    assert len(r["notify"]) == 1


def test_sent_deleted_hours_later_is_not_flagged(client):
    r = client.post("/api/v1/mailbox-activity", headers=A, json=_activity(
        [_removed("deleted", "s9", TUE_11AM - 7200, TUE_11AM, ["SENT"])])).json()
    assert r["findings"] == []


# 3. bank details sent outside -> high; the same to a colleague -> nothing
def test_sent_bank_details_outside_is_high(client):
    r = client.post("/api/v1/mailbox-activity", json=_activity([_sent("s2", VENDOR, BANK_BODY)]), headers=A).json()
    assert [f["severity"] for f in r["findings"]] == ["high"]
    assert "bank details" in r["findings"][0]["title"].lower()


def test_sent_bank_details_to_colleague_is_not_flagged(client):
    r = client.post("/api/v1/mailbox-activity", headers=A,
                    json=_activity([_sent("s3", "priya.raman@riverbend.example", BANK_BODY)])).json()
    assert r["findings"] == []


# 4. payment email trashed -> review (banner only); permanently deleted -> high + notice
def test_payment_email_trashed_is_review_and_deleted_is_high(client, real_contact):
    trashed = client.post("/api/v1/mailbox-activity", headers=A, json=_activity([_removed(
        "trashed", "m1", TUE_11AM - 600, TUE_11AM, ["INBOX", "TRASH"], VENDOR, "Invoice ACM-10438")])).json()
    assert [f["severity"] for f in trashed["findings"]] == ["review"] and trashed["notify"] == []
    deleted = client.post("/api/v1/mailbox-activity", headers=A, json=_activity([_removed(
        "deleted", "m1", TUE_11AM - 600, TUE_11AM + 60, ["TRASH"], VENDOR, "Invoice ACM-10438")])).json()
    assert [f["severity"] for f in deleted["findings"]] == ["high"] and len(deleted["notify"]) == 1


# 5. Google security alert deleted -> high
def test_deleted_security_alert_is_high(client):
    r = client.post("/api/v1/mailbox-activity", headers=A, json=_activity([_removed(
        "trashed", "g1", TUE_11AM - 60, TUE_11AM, ["INBOX", "TRASH"], "no-reply@accounts.google.com",
        "Security alert")])).json()
    assert [f["severity"] for f in r["findings"]] == ["high"]
    assert "security" in r["findings"][0]["title"].lower()


# 6. office hours raise the severity and say so
def test_rule_appearing_outside_office_hours_is_raised(client):
    client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER]), headers=A)
    client.clock["now"] = TUE_2AM
    r = client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER, MARK_READ]), headers=A).json()
    alert = r["alerts"]["items"][0]
    assert alert["severity"] == "high" and alert["outside_hours"] is True
    assert any("outside your office hours" in reason for reason in alert["reasons"])


def test_rule_appearing_in_office_hours_keeps_its_severity(client):
    client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER]), headers=A)
    r = client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER, MARK_READ]), headers=A).json()
    alert = r["alerts"]["items"][0]
    assert alert["severity"] == "review" and alert["outside_hours"] is False
    assert not any("office hours" in reason for reason in alert["reasons"])


def test_new_send_as_address_is_an_alert(client):
    client.post("/api/v1/mailbox-settings", json=_settings([]), headers=A)
    extra = [{"sendAsEmail": MAILBOX, "isPrimary": True}, {"sendAsEmail": "billing@acme-pay.example"}]
    r = client.post("/api/v1/mailbox-settings", json=_settings([], send_as=extra), headers=A).json()
    assert r["alerts"]["open"] == 1 and "billing@acme-pay.example" in r["alerts"]["items"][0]["title"]


# 7. a normal day -> nothing
def test_normal_activity_raises_nothing(client):
    r = client.post("/api/v1/mailbox-activity", headers=A, json=_activity([
        _sent("s4", "dana.whitfield@riverbend.example", "Lunch at noon?"),
        _removed("trashed", "n1", TUE_11AM - 3600, TUE_11AM, ["INBOX", "TRASH"], "news@digest.example",
                 "Pacific Dental Digest: October"),
    ])).json()
    assert r["findings"] == [] and r["alerts"]["open"] == 0


# writing style: only compared for outside recipients; banner only unless another warning is open
def test_style_mismatch_alone_is_review_and_with_another_alert_is_high(client):
    past = [_sent(f"p{i}", VENDOR, "Hi Sam,\nPaid via ACH today.\nJordan") for i in range(3)]
    client.post("/api/v1/mailbox-activity", json=_activity(past, baseline=True), headers=A)
    r = client.post("/api/v1/mailbox-activity", headers=A,
                    json=_activity([_sent("style-mismatch", VENDOR, "Dear Samuel, kindly revert ASAP.")])).json()
    assert [f["severity"] for f in r["findings"]] == ["review"] and r["notify"] == []
    client.post("/api/v1/mailbox-activity", headers=A, json=_activity([_removed(
        "trashed", "g2", TUE_11AM - 60, TUE_11AM, ["TRASH"], "no-reply@accounts.google.com", "Security alert")]))
    r2 = client.post("/api/v1/mailbox-activity", headers=A,
                     json=_activity([_sent("style-mismatch-2", VENDOR, "Dear Samuel, kindly revert ASAP.")])).json()
    assert [f["severity"] for f in r2["findings"]] == ["high"]


def test_baseline_events_never_alert(client):
    r = client.post("/api/v1/mailbox-activity", json=_activity([_sent("b1", VENDOR, BANK_BODY)], baseline=True),
                    headers=A).json()
    assert r["findings"] == [] and r["alerts"]["open"] == 0


# 8. banner on every card while a warning is open; "This was me" clears it
def _ingest(client, mid="m-card"):
    raw = _b64(f"Message-ID: <{mid}@x>\nAuthentication-Results: mx.google.com; spf=pass; dkim=pass; dmarc=pass\n"
               f"From: Sam Ortiz <{VENDOR}>\nTo: {MAILBOX}\nSubject: Invoice ACM-10438\n\n"
               "Invoice ACM-10438 for $17,200.00, PO-2026-0125, ACH to the usual account.")
    client.post("/api/v1/messages", headers=A, json={"provider": "gmail", "mailbox": MAILBOX, "message_id": mid,
                                                    "raw": raw})
    return client.get(f"/api/v1/messages/gmail/{mid}", params={"mailbox": MAILBOX}, headers=A).json()


def test_card_shows_mailbox_banner_until_acknowledged(client):
    assert _ingest(client)["mailbox_alerts"]["open"] == 0
    client.post("/api/v1/mailbox-activity", json=_activity([_sent("s5", VENDOR, BANK_BODY)]), headers=A)
    card = _ingest(client)
    assert card["mailbox_alerts"]["open"] == 1 and card["mailbox_alerts"]["summary"]
    assert "different device" in card["mailbox_alerts"]["advice"]
    ack = client.post("/api/v1/mailbox-alerts/ack", json={"provider": "gmail", "mailbox": MAILBOX}, headers=A).json()
    assert ack["alerts"]["open"] == 0
    assert _ingest(client)["mailbox_alerts"]["open"] == 0


def test_summary_falls_back_when_the_model_invents_a_value():
    alerts = [account_events.Alert(id="a", kind="sent", title="Email with bank details sent outside",
                                   severity="high", reasons=["Sent to x@y.com"], next_step="", at=0)]
    assert takeover.accept_summary("Someone sent bank details to x@y.com.", alerts)
    assert not takeover.accept_summary("Someone sent $5,000 to x@y.com.", alerts)


def test_security_config_gives_the_scanner_what_it_needs(client, placeholder_contact):
    r = client.get("/api/v1/security-config", headers=A).json()
    assert "riverbend.example" in r["org_domains"] and r["notify_ready"] is False
    assert "compliance_contacts" not in r  # addresses only travel inside a notice


# V1.5: an email placed in the mailbox (no delivery record from Gmail), e.g. a fake "approval" planted by an intruder
def _ingest_raw(client, mid, sender, subject, auth=True):
    headers = "Authentication-Results: mx.google.com; spf=pass; dkim=pass; dmarc=pass\n" if auth else ""
    raw = _b64(f"Message-ID: <{mid}@x>\n{headers}From: Sam Ortiz <{sender}>\nTo: {MAILBOX}\nSubject: {subject}\n\nHi")
    client.post("/api/v1/messages", headers=A, json={"provider": "gmail", "mailbox": MAILBOX, "message_id": mid,
                                                    "raw": raw})
    return account_events.open_alerts("riverbend", MAILBOX)


def test_payment_email_placed_without_delivery_is_high(client):
    alerts = _ingest_raw(client, "p1", VENDOR, "Re: Invoice ACM-10437 approved", auth=False)
    assert [a.severity for a in alerts] == ["high"] and "without being delivered" in alerts[0].title


def test_other_placed_email_is_review_and_delivered_mail_is_fine(client):
    assert _ingest_raw(client, "p2", "friend@example.com", "Lunch", auth=True) == []
    assert [a.severity for a in _ingest_raw(client, "p3", "friend@example.com", "Lunch", auth=False)] == ["review"]


def test_mail_from_the_mailbox_itself_is_not_flagged_as_placed(client):
    assert _ingest_raw(client, "p4", MAILBOX, "Note to self", auth=False) == []


# Regression (live, 2026-10-27): the compliance alert is sent FROM the mailbox, so it appears as sent mail to an
# outside address; it was style-checked as "doesn't read like you" -> a new alert -> a new email every minute.
def test_our_own_compliance_alert_is_not_checked_as_sent_mail(client, real_contact):
    ev = _sent("alert1", "compliance.test@gmail.com", "BEC Guard saw signs that someone else may be using ...")
    ev["subject"] = f"BEC Guard alert: possible takeover of {MAILBOX}"
    past = [_sent(f"p{i}", VENDOR, "Hi Sam,\nPaid via ACH today.\nJordan") for i in range(3)]
    client.post("/api/v1/mailbox-activity", json=_activity(past, baseline=True), headers=A)
    ev["message_id"] = "style-mismatch"  # the mock style check would call it a mismatch
    r = client.post("/api/v1/mailbox-activity", json=_activity([ev]), headers=A).json()
    assert r["findings"] == [] and r["notify"] == []


def test_compliance_notice_is_a_formatted_html_email(client, real_contact):
    client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER]), headers=A)
    r = client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER, HIDE_VENDOR]), headers=A).json()
    n = r["notify"][0]
    assert n["html"].startswith("<") and "Hi Compliance," in n["html"] and "<li>" in n["html"]
    assert "Possible takeover of " + MAILBOX in n["html"] and ">Details<" in n["html"] and ">What to do<" in n["html"]
    for text in (n["html"], n["body"]):  # professional: no warning symbols or "act now" labels (developer review)
        assert "⚠" not in text and "act now" not in text.lower() and "!" not in text
    assert "Hi Compliance," in n["body"] and "DETAILS" in n["body"]  # plain-text version


def test_notice_html_escapes_mail_content(client, real_contact):
    client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER]), headers=A)
    evil = {"id": "f-x", "criteria": {"from": VENDOR, "subject": "<script>x</script>"},
            "action": {"removeLabelIds": ["INBOX"]}}
    n = client.post("/api/v1/mailbox-settings", json=_settings([NEWSLETTER, evil]), headers=A).json()["notify"][0]
    assert "<script>" not in n["html"] and "&lt;script&gt;" in n["html"]


# Only mail from after BEC Guard started watching counts: the demo history (Jun-Oct) never raises anything.
JUNE = int(datetime(2026, 6, 10, 9, 0, tzinfo=PT).timestamp())


def test_deleting_an_email_from_before_monitoring_raises_nothing(client, real_contact):
    r = client.post("/api/v1/mailbox-activity", headers=A, json=_activity([
        _removed("deleted", "old1", JUNE, TUE_11AM, ["INBOX"], VENDOR, "Invoice ACM-10435"),
        _removed("trashed", "old2", JUNE, TUE_11AM, ["SENT", "TRASH"], MAILBOX, "Re: Invoice ACM-10435"),
        _removed("deleted", "unknown", None, TUE_11AM, []),  # never seen by BEC Guard: can't tell, so nothing
    ])).json()
    assert r["findings"] == [] and r["notify"] == []


def test_old_email_without_delivery_record_is_not_flagged_as_placed(client):
    raw = _b64(f"Message-ID: <old3@x>\nDate: Wed, 10 Jun 2026 09:00:00 -0700\nFrom: Sam Ortiz <{VENDOR}>\n"
               f"To: {MAILBOX}\nSubject: Invoice ACM-10435\n\nHi")
    client.post("/api/v1/messages", headers=A, json={"provider": "gmail", "mailbox": MAILBOX, "message_id": "old3",
                                                    "raw": raw})
    assert account_events.open_alerts("riverbend", MAILBOX) == []


def test_monitoring_starts_at_the_first_check(client):
    account_events.reset()
    client.post("/api/v1/mailbox-activity", json=_activity([], baseline=True), headers=A)
    assert account_events.monitoring_since("riverbend", MAILBOX) == TUE_11AM


def test_summary_with_exclamation_marks_is_rejected():
    alerts = [account_events.Alert(id="a", kind="setting", title="New filter", severity="high", reasons=[],
                                   next_step="", at=0)]
    assert not takeover.accept_summary("Your mailbox has been hacked!", alerts)


# Live (2026-10-27): two notices with the same subject were threaded by Gmail, which hid the repeated parts ("...").
def test_each_notice_has_its_own_subject_and_a_follow_up_says_update(client, real_contact):
    client.post("/api/v1/mailbox-activity", json=_activity([_sent("s7", VENDOR, BANK_BODY)]), headers=A)
    first = client.post("/api/v1/mailbox-activity", json=_activity([]), headers=A).json()  # already notified
    client.clock["now"] = TUE_11AM + 60
    second = client.post("/api/v1/mailbox-activity", headers=A, json=_activity(
        [_removed("trashed", "s7", TUE_11AM, TUE_11AM + 60, ["SENT", "TRASH"])])).json()["notify"][0]
    assert first["notify"] == []
    assert second["subject"].startswith(takeover.NOTICE_SUBJECT + MAILBOX) and "update" in second["subject"].lower()
    assert "11:00 AM" in second["html"]  # refers to the first alert
    assert "deleted soon after sending" in second["html"].lower() and "bank details" not in second["html"].lower()


def test_unchanged_settings_are_explained_once(client, monkeypatch):
    from app.phase_b import mailbox_check
    calls = []
    real = mailbox_check.complete_json
    async def counting(**kw):
        calls.append(kw["step"])
        return await real(**kw)
    monkeypatch.setattr(mailbox_check, "complete_json", counting)
    for _ in range(3):
        client.post("/api/v1/mailbox-settings", json=_settings([HIDE_VENDOR]), headers=A)
    assert calls.count("mailbox_explain") == 1
