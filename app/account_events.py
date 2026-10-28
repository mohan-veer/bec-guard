"""Signs that the organization's OWN mailbox is being taken over (in memory, per tenant).

1. Mailbox settings that are new since the last check (a hacker adds a hidden filter or forwarding right after
   logging in). The first check of a mailbox becomes its baseline.
2. The mail provider's own security emails ("New sign-in", "Critical security alert", forwarding added). Only
   recorded when DMARC passes for the provider's domain, so a spoofed "Google" alert is ignored.
3. Alerts from mailbox activity and new settings (rules in app/phase_b/takeover.py), open until someone clicks
   "This was me"; plus what the scanner told us about sent mail (deleted-soon checks, writing-style samples).
We can't see another company's logins (e.g. a vendor's): that side is covered by the email content checks.
"""
import re
import time
from typing import Literal

from pydantic import BaseModel

from app.phase_a.models import Email

PROVIDER_ALERT_DOMAINS = {"accounts.google.com": "google_security_alert", "google.com": "google_security_alert",
                          "accountprotection.microsoft.com": "microsoft_security_alert",
                          "cc.yahoo-inc.com": "yahoo_security_alert"}
ALERT_SUBJECT = re.compile(r"security alert|new sign-in|sign-in attempt|suspicious|password (was )?changed|"
                           r"forwarding|recovery (email|phone)|new device", re.IGNORECASE)

SENT_MAX = 200          # sent emails remembered per mailbox (arbitrary)
STYLE_SAMPLES = 5      # past outside emails kept for the writing-style comparison (same as the vendor check)

MailboxKey = tuple[str, str]
_settings_seen: dict[MailboxKey, set[str]] = {}
_events: dict[str, list[dict]] = {}


class Alert(BaseModel):
    id: str
    kind: str                      # sent / trashed / deleted / setting
    title: str
    severity: Literal["high", "review"]
    reasons: list[str]
    next_step: str
    at: float                      # when it happened (or was first seen)
    outside_hours: bool = False
    notified: bool = False         # compliance contact emailed
    acknowledged: bool = False     # "This was me"


_alerts: dict[MailboxKey, dict[str, Alert]] = {}
_sent: dict[MailboxKey, dict[str, dict]] = {}
_style: dict[MailboxKey, list[str]] = {}
_since: dict[MailboxKey, float] = {}   # when BEC Guard started watching this mailbox
_last_notice: dict[MailboxKey, float] = {}


def _k(tenant: str, mailbox: str) -> MailboxKey:
    return tenant, mailbox.lower()


def reset() -> None:
    for store in (_settings_seen, _events, _alerts, _sent, _style, _since, _last_notice):
        store.clear()


def start_monitoring(tenant: str, mailbox: str, at: float) -> None:
    """The first check of a mailbox. Mail sent or received before this is never alerted on (like an antivirus:
    protection starts at install)."""
    _since.setdefault(_k(tenant, mailbox), at)


def monitoring_since(tenant: str, mailbox: str) -> float | None:
    return _since.get(_k(tenant, mailbox))


def last_notice(tenant: str, mailbox: str) -> float | None:
    return _last_notice.get(_k(tenant, mailbox))


def record_notice(tenant: str, mailbox: str, at: float) -> None:
    _last_notice[_k(tenant, mailbox)] = at


def add_alert(tenant: str, mailbox: str, alert: Alert) -> bool:
    """False if this alert (same id) was already raised."""
    alerts = _alerts.setdefault(_k(tenant, mailbox), {})
    if alert.id in alerts:
        return False
    alerts[alert.id] = alert
    return True


def open_alerts(tenant: str, mailbox: str) -> list[Alert]:
    alerts = [a for a in _alerts.get(_k(tenant, mailbox), {}).values() if not a.acknowledged]
    return sorted(alerts, key=lambda a: (a.severity != "high", -a.at))


def acknowledge(tenant: str, mailbox: str) -> None:
    for a in _alerts.get(_k(tenant, mailbox), {}).values():
        a.acknowledged = True


def remember_sent(tenant: str, mailbox: str, message_id: str, meta: dict) -> None:
    sent = _sent.setdefault(_k(tenant, mailbox), {})
    sent[message_id] = meta
    while len(sent) > SENT_MAX:
        sent.pop(next(iter(sent)))


def sent_meta(tenant: str, mailbox: str, message_id: str) -> dict | None:
    return _sent.get(_k(tenant, mailbox), {}).get(message_id)


def style_samples(tenant: str, mailbox: str) -> list[str]:
    return list(_style.get(_k(tenant, mailbox), []))


def add_style_sample(tenant: str, mailbox: str, body: str) -> None:
    samples = _style.setdefault(_k(tenant, mailbox), [])
    samples.append(body)
    del samples[:-STYLE_SAMPLES]


def settings_changes(tenant: str, mailbox: str, item_ids: set[str]) -> dict:
    """Compares this check's rules/forwarding ids with the previous check of the same mailbox."""
    k = _k(tenant, mailbox)
    previous = _settings_seen.get(k)
    _settings_seen[k] = set(item_ids)
    if previous is None:
        return {"first_check": True, "new": []}
    return {"first_check": False, "new": sorted(item_ids - previous)}


def record_if_provider_alert(tenant: str, mailbox: str, e: Email) -> dict | None:
    kind = PROVIDER_ALERT_DOMAINS.get(e.from_domain)
    if not kind or e.dmarc != "pass" or not ALERT_SUBJECT.search(e.subject or ""):
        return None
    event = {"kind": kind, "mailbox": mailbox.lower(), "subject": e.subject, "from": e.from_addr,
             "received": e.date.isoformat() if e.date else None, "recorded_at": time.time()}
    _events.setdefault(tenant, []).append(event)
    return event


def events(tenant: str) -> list[dict]:
    return sorted(_events.get(tenant, []), key=lambda ev: ev["recorded_at"], reverse=True)
