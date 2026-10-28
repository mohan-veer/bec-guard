"""Signs that someone else is using the organization's own mailbox (rules decide; Nemotron only writes text).

Activity, reported by the mail-side scanner from the provider's change history:
- sent:    an email to someone outside the company with bank details -> high; one that doesn't read like the owner's
           past outside emails (Nemotron Super) -> review, high if another warning is already open
- trashed / deleted: a sent email removed soon after sending -> high; a provider security email removed -> high;
           a payment-related email moved to Trash -> review, permanently deleted -> high
Settings: a filter / forwarding / send-as address / POP access that is new since the last check (mailbox_check.py).
Only mail sent or received after BEC Guard started watching the mailbox counts (the demo history never alerts).
Anything outside office hours is raised to high. High alerts are emailed once to the compliance contact, whose
address lives on the server (security.json), so whoever is in the mailbox can't change it.
"""
import base64
import binascii
import html
import re
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app import account_events, jobs
from app.account_events import Alert
from app.clients.llm import complete_json
from app.config import load_settings
from app.phase_a.card import _VALUE
from app.phase_a.content import STYLE_SYSTEM, extract_payment_details
from app.phase_a.data import load_ledger, load_org, load_security
from app.phase_a.entity import FREE_EMAIL_DOMAINS
from app.phase_a.parse import parse_eml
from app.phase_b.mailbox_check import PAYMENT_WORDS, Finding

NOTICE_SUBJECT = "BEC Guard alert: possible takeover of "
FOLLOW_UP_WINDOW = 60 * 60     # a notice within this of the previous one is an "update" (arbitrary)
SOON_AFTER_SENDING = 30 * 60   # a sent email deleted within this is "covering tracks" (arbitrary, never measured)
PLACEHOLDER_SUFFIX = ".invalid"
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ADVICE = ("Until this is cleared, confirm any payment or bank change by phone, from a different device. If this "
          "wasn't you, change your password and tell your IT or compliance contact.")
NEXT_STEPS = {
    "sent_bank": "If you didn't send this, call the recipient now and tell them not to use these details, then "
                 "change your password and sign out of all sessions.",
    "sent_style": "If you didn't write this, change your password, sign out of all sessions, and warn the recipient.",
    "sent_deleted": "Check Trash for the email. If you didn't send it, warn the recipient, change your password and "
                    "sign out of all sessions.",
    "security_deleted": "Open your Google Account's security page from a different device and review recent "
                        "sign-ins and devices.",
    "payment_removed": "Check Trash for the email. If you didn't remove it, someone may be hiding a payment "
                       "conversation: change your password and tell your IT or compliance contact.",
    "setting": "If you didn't add this, remove it, change your password and sign out of all sessions.",
}


def now() -> float:
    return time.time()


# ---------- organization settings (office hours, compliance contact) ----------

class OfficeHours(BaseModel):
    timezone: str = "America/Los_Angeles"
    days: list[int] = [0, 1, 2, 3, 4]       # Monday = 0
    start: str = "08:00"
    end: str = "18:00"


class Contact(BaseModel):
    name: str = ""
    email: str


class SecuritySettings(BaseModel):
    office_hours: OfficeHours = OfficeHours()  # default: a guess, arbitrary
    compliance_contacts: list[Contact] = []


def security_settings() -> SecuritySettings:
    return SecuritySettings.model_validate(load_security())


def notify_recipients(s: SecuritySettings) -> list[str]:
    return [c.email for c in s.compliance_contacts if "@" in c.email and not c.email.endswith(PLACEHOLDER_SUFFIX)]


def _local(ts: float, oh: OfficeHours) -> datetime:
    return datetime.fromtimestamp(ts, ZoneInfo(oh.timezone))


def outside_hours(ts: float, oh: OfficeHours) -> bool:
    t = _local(ts, oh)
    start, end = dtime.fromisoformat(oh.start), dtime.fromisoformat(oh.end)
    return t.weekday() not in oh.days or not (start <= t.time() < end)


def _hours_text(ts: float, oh: OfficeHours) -> str:
    t = _local(ts, oh)
    days = f"{DAY_NAMES[min(oh.days)]}–{DAY_NAMES[max(oh.days)]}" if oh.days else "no days"
    return (f"Happened at {t.strftime('%-I:%M %p')} on {DAY_NAMES[t.weekday()]}, outside your office hours "
            f"({days} {oh.start}–{oh.end})")


def _with_hours(a: Alert, oh: OfficeHours) -> Alert:
    if not outside_hours(a.at, oh):
        return a
    return a.model_copy(update={"severity": "high", "outside_hours": True,
                                "reasons": a.reasons + [_hours_text(a.at, oh)]})


# ---------- who is who ----------

def org_domains(mailbox: str) -> list[str]:
    return load_org().domains + [mailbox.lower().rsplit("@", 1)[-1]]  # own mailbox domain is internal


def outside(addresses: list[str], mailbox: str) -> list[str]:
    """Recipients outside the company. The mailbox's own domain only counts as internal when it isn't a free
    provider: two gmail.com addresses are not colleagues."""
    internal = set(load_org().domains) | {p.email.lower() for p in load_org().people} | {mailbox.lower()}
    own = mailbox.lower().rsplit("@", 1)[-1]
    if own not in FREE_EMAIL_DOMAINS:
        internal.add(own)
    return [a for a in (x.lower() for x in addresses) if a not in internal and a.rsplit("@", 1)[-1] not in internal]


def known_senders(mailbox: str) -> dict[str, str]:
    """Address or company domain -> who it is, for filters that hide a real vendor's or colleague's mail."""
    known = {}
    for v in load_ledger().vendors:
        for c in v.contacts:
            known[c.email.lower()] = f"{v.name} (a vendor on file)"
        for d in v.domains:
            if d not in FREE_EMAIL_DOMAINS:
                known[d.lower()] = f"{v.name} (a vendor on file)"
    for p in load_org().people:
        if p.email.lower() != mailbox.lower():
            known[p.email.lower()] = f"{p.name} ({p.role})"
    return known


def _vendor_of(sender: str) -> str | None:
    sender = sender.lower()
    for v in load_ledger().vendors:
        if sender in {c.email.lower() for c in v.contacts} or sender.rsplit("@", 1)[-1] in v.domains:
            return v.name
    return None


# ---------- activity ----------

class ActivityEvent(BaseModel):
    kind: str = Field(pattern=r"^(sent|trashed|deleted)$")
    message_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_\-=.:+]+$")
    message_time: float | None = None   # when the email was sent / received (epoch seconds)
    detected_at: float | None = None    # when the scanner saw the change
    labels: list[str] = Field(default=[], max_length=50)
    sender: str = Field(default="", alias="from", max_length=320)
    to: list[str] = Field(default=[], max_length=100)
    subject: str = Field(default="", max_length=500)
    raw: str | None = Field(default=None, max_length=jobs.MAX_RAW_B64)  # only for sent mail going outside


def _body(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return parse_eml(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))).body_text
    except (binascii.Error, ValueError):
        return ""


def _bank_text(body: str) -> str | None:
    d = extract_payment_details(body)
    parts = [f"bank {d.bank_name}" if d.bank_name else "", f"routing {d.routing_number}" if d.routing_number else "",
             f"account ending {d.account_last4}" if d.account_last4 else ""]
    return ", ".join(p for p in parts if p) or None


async def _style_mismatch(message_id: str, body: str, past: list[str]) -> str | None:
    out = await complete_json(
        step="sent_style", key=message_id, model=load_settings().model_super,
        messages=[{"role": "system", "content": STYLE_SYSTEM},
                  {"role": "user", "content": "PAST EMAILS:\n" + "\n\n---\n\n".join(past) +
                   f"\n\nNEW EMAIL:\n{body[:4000]}"}],
        schema=_StyleOut, default=_StyleOut(),
    )
    return (out.reason or "different greeting or tone") if out.mismatch else None


class _StyleOut(BaseModel):
    mismatch: bool = False
    reason: str = ""


def _before_monitoring(tenant: str, mailbox: str, t: float | None) -> bool:
    since = account_events.monitoring_since(tenant, mailbox)
    return t is None or since is None or t < since


async def _check_sent(tenant: str, mailbox: str, ev: ActivityEvent, baseline: bool) -> list[Alert]:
    at = ev.message_time or ev.detected_at or now()
    out_to = outside(ev.to, mailbox)
    account_events.remember_sent(tenant, mailbox, ev.message_id,
                                 {"time": at, "to": out_to or ev.to, "subject": ev.subject})
    if not out_to or (not baseline and _before_monitoring(tenant, mailbox, at)):
        return []
    if ev.subject.startswith(NOTICE_SUBJECT) and set(out_to) <= set(notify_recipients(security_settings())):
        return []  # our own compliance alert (sent from this mailbox): never checked, or it would alert about itself
    body = _body(ev.raw)
    if baseline:
        if body:
            account_events.add_style_sample(tenant, mailbox, body)
        return []
    alerts = []
    sent_to = f"Sent to {', '.join(out_to)}" + (f": \"{ev.subject}\"" if ev.subject else "")
    if bank := _bank_text(body):
        alerts.append(Alert(id=f"sent_bank:{ev.message_id}", kind="sent", severity="high", at=at,
                            title="Email with bank details sent outside the company",
                            reasons=[sent_to, f"Contains {bank}"], next_step=NEXT_STEPS["sent_bank"]))
    past = account_events.style_samples(tenant, mailbox)
    if body and len(past) >= 2:
        if reason := await _style_mismatch(ev.message_id, body, past):
            other_open = bool(alerts or account_events.open_alerts(tenant, mailbox))
            alerts.append(Alert(id=f"sent_style:{ev.message_id}", kind="sent", at=at,
                                severity="high" if other_open else "review",
                                title="A sent email doesn't read like your past emails",
                                reasons=[sent_to, f"Writing style differs ({reason})"],
                                next_step=NEXT_STEPS["sent_style"]))
    if body:
        account_events.add_style_sample(tenant, mailbox, body)
    return alerts


def _check_removed(tenant: str, provider: str, mailbox: str, ev: ActivityEvent) -> list[Alert]:
    at = ev.detected_at or now()
    gone = "permanently deleted" if ev.kind == "deleted" else "moved to Trash"
    job = jobs.store.get(jobs.key(tenant, provider, mailbox, ev.message_id))
    sender = (ev.sender or (job.sender if job else "") or "").lower()
    subject = ev.subject or (job.subject if job else "") or ""
    about = [r for r in (f"From {sender}" if sender else "", f"Subject: {subject}" if subject else "") if r]

    sent = account_events.sent_meta(tenant, mailbox, ev.message_id)
    msg_time = ev.message_time or (sent or {}).get("time") or (job.email_time or job.created if job else None)
    if _before_monitoring(tenant, mailbox, msg_time):
        return []  # an email from before BEC Guard was watching (or one it never saw): not ours to judge
    if "SENT" in ev.labels or sent:
        sent_at = ev.message_time or (sent or {}).get("time")
        if not sent_at or at - sent_at > SOON_AFTER_SENDING:
            return []
        to = (sent or {}).get("to") or ev.to
        subject = subject or (sent or {}).get("subject", "")
        reasons = [r for r in (f"Sent to {', '.join(to)}" if to else "", f"Subject: {subject}" if subject else "") if r]
        reasons.append(f"{gone.capitalize()} {max(1, round((at - sent_at) / 60))} min after it was sent")
        return [Alert(id=f"{ev.kind}:{ev.message_id}", kind=ev.kind, severity="high", at=at, reasons=reasons,
                      title="A sent email was deleted soon after sending", next_step=NEXT_STEPS["sent_deleted"])]

    domain = sender.rsplit("@", 1)[-1]
    if domain in account_events.PROVIDER_ALERT_DOMAINS:
        return [Alert(id=f"{ev.kind}:{ev.message_id}", kind=ev.kind, severity="high", at=at, reasons=about,
                      title=f"A security email from your mail provider was {gone}",
                      next_step=NEXT_STEPS["security_deleted"])]

    why = []
    if vendor := _vendor_of(sender):
        why.append(f"From {vendor}, a vendor on file")
    if words := sorted({w.lower() for w in PAYMENT_WORDS.findall(subject)}):
        why.append(f"About payment ({', '.join(words)})")
    if bank := _bank_text(_body(ev.raw)):
        why.append(f"Contains {bank}")
    if job and job.label:
        why.append("BEC Guard had flagged this email")
    if not why:
        return []
    return [Alert(id=f"{ev.kind}:{ev.message_id}", kind=ev.kind, at=at, reasons=about + why,
                  severity="high" if ev.kind == "deleted" else "review",
                  title=f"A payment-related email was {gone}", next_step=NEXT_STEPS["payment_removed"])]


async def check_activity(tenant: str, provider: str, mailbox: str, events: list[ActivityEvent],
                         baseline: bool) -> list[Alert]:
    """Runs the rules, stores new alerts, returns the new ones."""
    oh = security_settings().office_hours
    new = []
    for ev in events:
        found = (await _check_sent(tenant, mailbox, ev, baseline) if ev.kind == "sent"
                 else [] if baseline else _check_removed(tenant, provider, mailbox, ev))
        for a in found:
            a = _with_hours(a, oh)
            if account_events.add_alert(tenant, mailbox, a):
                new.append(a)
    return new


_DELIVERY_RECORD = re.compile(rb"^(ARC-)?Authentication-Results:", re.IGNORECASE | re.MULTILINE)


def check_placed(tenant: str, mailbox: str, message_id: str, raw: bytes, e) -> Alert | None:
    """Mail Gmail delivers always carries its delivery checks (Authentication-Results). Without them, the email was
    put into the mailbox directly (an app or someone signed in), not sent: e.g. a planted "approval" email."""
    headers = raw.split(b"\r\n\r\n", 1)[0].split(b"\n\n", 1)[0]
    if _DELIVERY_RECORD.search(headers) or e.from_addr == mailbox.lower():
        return None
    if _before_monitoring(tenant, mailbox, e.date.timestamp() if e.date else now()):
        return None  # e.g. the imported demo history, opened in the sidebar
    payment = bool(PAYMENT_WORDS.search(e.subject or "")) or bool(_vendor_of(e.from_addr))
    reasons = [f"From {e.from_addr}" + (f': "{e.subject}"' if e.subject else ""),
               "It has no delivery record from Gmail, so it was placed in your mailbox directly, not sent to you"]
    a = _with_hours(Alert(id=f"placed:{message_id}", kind="placed", severity="high" if payment else "review", at=now(),
                          title="An email appeared in your mailbox without being delivered", reasons=reasons,
                          next_step="Don't act on this email. If you didn't import it, change your password and tell "
                                    "your IT or compliance contact."), security_settings().office_hours)
    return a if account_events.add_alert(tenant, mailbox, a) else None


# ---------- settings ----------

def settings_alerts(tenant: str, mailbox: str, findings: list[Finding], new_ids: list[str]) -> list[Alert]:
    """New risky filters / forwarding (from the settings report) and new send-as / POP access become alerts."""
    oh, at = security_settings().office_hours, now()
    found = [Alert(id=f.id, kind="setting", severity=f.severity, at=at, reasons=f.reasons, next_step=f.next_step,
                   title=f"New {'forwarding' if f.kind == 'forwarding' else 'filter'}: {f.rule_name}")
             for f in findings if f.new_since_last_check]
    for i in new_ids:
        if i.startswith("sendas:"):
            found.append(Alert(id=i, kind="setting", severity="review", at=at, next_step=NEXT_STEPS["setting"],
                               title=f'New "send mail as" address: {i[7:]}',
                               reasons=["Lets this mailbox send email that appears to come from that address"]))
        elif i == "pop":
            found.append(Alert(id=i, kind="setting", severity="review", at=at, next_step=NEXT_STEPS["setting"],
                               title="POP download was turned on",
                               reasons=["Lets another program download a copy of all your mail"]))
    new = []
    for a in found:
        a = _with_hours(a, oh)
        if account_events.add_alert(tenant, mailbox, a):
            new.append(a)
    return new


# ---------- banner, summary, compliance notice ----------

SUMMARY_SYSTEM = (
    "You warn an office worker that their mailbox may be in someone else's hands. Given the alerts, write ONE or TWO "
    "short, calm, professional sentences on what they add up to (no exclamation marks). Use only the facts given; "
    'never add numbers, addresses or names. Reply with JSON only: {"summary": "..."}.'
)
MAX_SUMMARY_WORDS = 60
_summaries: dict[tuple, str] = {}


class _SummaryOut(BaseModel):
    summary: str = ""


def _norm(v: str) -> str:
    return re.sub(r"[^\w@.$]", "", v.lower())


def accept_summary(text: str, alerts: list[Alert]) -> bool:
    """The summary may only reuse values (addresses, amounts, numbers) that appear in the alerts."""
    if not text or len(text.split()) > MAX_SUMMARY_WORDS or "!" in text:
        return False
    facts = " ".join(a.title + " " + " ".join(a.reasons) for a in alerts)
    allowed = {_norm(v) for v in _VALUE.findall(facts)}
    return all(_norm(v) in allowed for v in _VALUE.findall(text))


def _fallback_summary(alerts: list[Alert]) -> str:
    n = len(alerts)
    return f"{n} sign{'s' if n > 1 else ''} that someone else may be using this mailbox: " + \
        "; ".join(a.title for a in alerts[:3]) + ("…" if n > 3 else ".")


async def summary(alerts: list[Alert]) -> str:
    key = tuple(sorted(a.id for a in alerts))
    if key not in _summaries:
        facts = "\n".join(f"- {a.title}: {'; '.join(a.reasons)}" for a in alerts)
        st = load_settings()
        out = await complete_json(
            step="takeover_summary", key="|".join(key), model=st.model_ultra, fallback_model=st.model_super,
            messages=[{"role": "system", "content": SUMMARY_SYSTEM}, {"role": "user", "content": facts}],
            schema=_SummaryOut, default=_SummaryOut(),
        )
        text = out.summary.strip()
        _summaries[key] = text if accept_summary(text, alerts) else _fallback_summary(alerts)
    return _summaries[key]


async def alerts_view(tenant: str, mailbox: str) -> dict:
    alerts = account_events.open_alerts(tenant, mailbox)
    if not alerts:
        return {"open": 0, "high": 0, "summary": "", "advice": "", "items": []}
    return {"open": len(alerts), "high": sum(a.severity == "high" for a in alerts), "summary": await summary(alerts),
            "advice": ADVICE,
            "items": [a.model_dump(include={"id", "kind", "title", "severity", "reasons", "next_step", "at",
                                            "outside_hours"}) for a in alerts]}


async def take_notices(tenant: str, mailbox: str) -> tuple[list[dict], str]:
    """Compliance emails for high alerts not yet notified (each alert is emailed once). Returns (notices, why not)."""
    pending = [a for a in account_events.open_alerts(tenant, mailbox) if a.severity == "high" and not a.notified]
    if not pending:
        return [], ""
    to = notify_recipients(security_settings())
    if not to:
        return [], "No compliance contact is set up yet, so no alert email was sent."
    s = security_settings()
    names = [c.name for c in s.compliance_contacts if c.email in to and c.name]
    text = await summary(pending)
    at, previous = now(), account_events.last_notice(tenant, mailbox)
    previous = previous if previous and at - previous <= FOLLOW_UP_WINDOW else None
    notice = _notice(mailbox, names[0] if len(names) == 1 else "", text, pending, s.office_hours, previous)
    account_events.record_notice(tenant, mailbox, at)
    # Its own subject (with the time): Gmail threads same-subject emails and hides their repeated parts behind "...".
    stamp = _local(at, s.office_hours).strftime("%a %-I:%M %p")
    subject = NOTICE_SUBJECT + mailbox + (f" - update ({stamp})" if previous else f" ({stamp})")
    for a in pending:
        a.notified = True
    return [{"to": to, "subject": subject, **notice}], ""


_STEPS = ["Call the mailbox owner on a known number (not by replying to this email) and ask whether they did this.",
          "If they didn't: change the mailbox password, sign out all sessions, and remove the items listed above.",
          "Until it's cleared, confirm any payment or bank change by phone, from a different device."]
_FOOTER = ("Sent by BEC Guard from the mailbox itself, so whoever is using it may see this email in Sent. "
           "Please don't reply to it.")


def _notice(mailbox: str, name: str, text: str, alerts: list[Alert], oh: OfficeHours,
            previous: float | None = None) -> dict:
    """The compliance email, as HTML and plain text: a short headline box, the details of each alert, what to do.
    Written like a professional security notice: one colour accent, no warning symbols or "act now" labels."""
    hi = f"Hi {name}," if name else "Hello,"
    when = lambda a: _local(a.at, oh).strftime("%a %b %-d, %-I:%M %p")  # noqa: E731
    headline = (f"Update: new activity on {mailbox} since the alert at {_local(previous, oh).strftime('%-I:%M %p')}"
                if previous else f"Possible takeover of {mailbox}")
    e = html.escape
    items = "".join(
        f'<li style="margin-bottom:10px"><b>{e(a.title)}</b> <span style="color:#64748b">({e(when(a))})</span>'
        '<ul style="margin:4px 0">' + "".join(f"<li>{e(r)}</li>" for r in a.reasons) + "</ul></li>" for a in alerts)
    steps = "".join(f"<li>{e(s)}</li>" for s in _STEPS)
    html_body = (
        '<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5;color:#1e293b;max-width:640px">'
        f"<p>{e(hi)}</p>"
        '<div style="border-left:4px solid #b91c1c;background:#fef2f2;padding:10px 12px;margin:12px 0">'
        f'<b style="color:#991b1b">{e(headline)}</b><br>{e(text)}</div>'
        f'<p style="margin-bottom:4px"><b>Details</b></p><ul style="padding-left:20px;margin-top:4px">{items}</ul>'
        f'<p style="margin-bottom:4px"><b>What to do</b></p><ol style="padding-left:20px;margin-top:4px">{steps}</ol>'
        f'<p style="color:#64748b;font-size:12px;border-top:1px solid #e2e8f0;padding-top:8px">{e(_FOOTER)}</p></div>')
    plain = (f"{hi}\n\n{headline}\n{text}\n\nDETAILS\n" +
             "\n".join(f"- {a.title} ({when(a)})\n    " + "\n    ".join(a.reasons) for a in alerts) +
             "\n\nWHAT TO DO\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(_STEPS, 1)) + f"\n\n{_FOOTER}")
    return {"body": plain, "html": html_body}


def reset() -> None:
    _summaries.clear()
