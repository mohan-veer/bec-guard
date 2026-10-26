"""Risky inbox rule / forwarding detection (rules decide), plus a one-line Nemotron Super explanation per finding.

Severity:
- high:   forwards outside the org; or hides mail (delete, mark read, obscure folder, skip inbox) AND triggers on
          payment words; or has a meaningless name AND hides mail
- review: deletes / marks read / moves to an obscure folder on its own; or a meaningless name on its own
- not flagged: skipping the inbox or moving to an ordinary folder on its own (very common for newsletters)
"""
import re
from typing import Literal

from pydantic import BaseModel

from app.clients.llm import complete_json
from app.clients.mailbox import MailboxSnapshot, Rule
from app.config import load_settings

PAYMENT_WORDS = re.compile(r"invoice|payment|\bpay\b|wire|bank|\bach\b|remit|transfer|account|payroll|\bw-?2\b|"
                           r"direct deposit", re.IGNORECASE)
OBSCURE_FOLDERS = {"rss feeds", "rss subscriptions", "rss", "conversation history", "archive", "junk email",
                   "sync issues", "notes"}

NEXT_STEPS = {
    ("rule", "high"): "Delete this rule, change your email password, and sign out of all sessions. "
                      "Then tell whoever handles your IT.",
    ("rule", "review"): "Check whether you created this rule. If you didn't, delete it and change your password.",
    ("forwarding", "high"): "Remove this forwarding, change your email password, and sign out of all sessions.",
    ("forwarding", "review"): "If you don't recognize this address, remove it and change your password.",
}

LIMITS_COMMON = [
    "Sign-in locations aren't checked: Microsoft only provides sign-in logs with an Entra ID P1 license.",
    "Read-only: BEC Guard never changes or deletes your rules.",
]
LIMITS = {
    "outlook": ["Account-wide forwarding set in Outlook settings or by an admin isn't visible through this API; "
                "inbox rules are checked."],
    "gmail": ["Custom label names aren't read (that permission could also change labels); delete, mark-read, "
              "archive and forward actions are checked."],
}


class Finding(BaseModel):
    id: str
    kind: Literal["rule", "forwarding"]
    rule_name: str
    severity: Literal["high", "review"]
    reasons: list[str]
    next_step: str
    explanation: str | None = None


class MailboxReport(BaseModel):
    provider: str
    source: str
    rules_checked: int
    rules_disabled: int
    findings: list[Finding]
    limits: list[str]
    notes: list[str] = []


def _external(address: str, org_domains: list[str]) -> bool:
    return address.rsplit("@", 1)[-1] not in org_domains


def _meaningless(name: str) -> bool:
    return len(re.sub(r"[\W_]+", "", name)) <= 1


def _check_rule(r: Rule, org_domains: list[str]) -> Finding | None:
    outside = [a for a in r.forward_to if _external(a, org_domains)]
    obscure = bool(r.move_to and r.move_to_named and r.move_to.lower() in OBSCURE_FOLDERS)
    unnamed_folder = bool(r.move_to and not r.move_to_named)
    strong_hide = r.delete or r.mark_read or obscure
    hides = strong_hide or r.skips_inbox or unnamed_folder
    payment = sorted({k for k in r.keywords if PAYMENT_WORDS.search(k)})
    meaningless = r.provider == "outlook" and _meaningless(r.name)

    if outside or (hides and payment) or (meaningless and hides):
        severity = "high"
    elif strong_hide or meaningless:
        severity = "review"
    else:
        return None

    reasons = [f"Forwards mail to an outside address: {a}" for a in outside]
    if payment:
        reasons.append(f"Triggers on payment words: {', '.join(payment)}")
    if r.delete:
        reasons.append("Deletes matching mail")
    if r.mark_read:
        reasons.append("Marks matching mail as read, so it doesn't stand out")
    if obscure:
        reasons.append(f'Moves mail to "{r.move_to}", a folder people rarely check')
    if unnamed_folder and (payment or meaningless):
        reasons.append("Moves mail to a folder (name not available)")
    if r.skips_inbox and (payment or meaningless or outside):
        reasons.append("Skips the inbox (archives matching mail)")
    if meaningless:
        reasons.append(f'Has a meaningless name ("{r.name}"), a common way to hide a rule')
    return Finding(id=f"rule:{r.id}", kind="rule", rule_name=r.name or "(no name)", severity=severity,
                   reasons=reasons, next_step=NEXT_STEPS[("rule", severity)])


def check_mailbox(snap: MailboxSnapshot, org_domains: list[str]) -> MailboxReport:
    enabled = [r for r in snap.rules if r.enabled]
    findings = [f for r in enabled if (f := _check_rule(r, org_domains))]

    for a in snap.forwarding:
        if _external(a.email, org_domains):
            severity = "high" if a.status == "accepted" else "review"
            status = "verified and ready to use" if a.status == "accepted" else f"status: {a.status or 'unknown'}"
            findings.append(Finding(id=f"fwd:{a.email}", kind="forwarding", rule_name=f"Forwarding address {a.email}",
                                    severity=severity, reasons=[f"Mail can be forwarded to {a.email} ({status})"],
                                    next_step=NEXT_STEPS[("forwarding", severity)]))

    af = snap.auto_forward
    if af.enabled and af.email and _external(af.email, org_domains):
        reasons = [f"All incoming mail is automatically forwarded to {af.email}"]
        if af.disposition == "trash":
            reasons.append("Forwarded mail is then deleted from your inbox")
        elif af.disposition in ("markRead", "archive"):
            reasons.append("Forwarded mail is then hidden from your inbox")
        findings.append(Finding(id="autofwd", kind="forwarding", rule_name="Automatic forwarding", severity="high",
                                reasons=reasons, next_step=NEXT_STEPS[("forwarding", "high")]))

    findings.sort(key=lambda f: f.severity != "high")
    return MailboxReport(provider=snap.provider, source=snap.source, rules_checked=len(snap.rules),
                         rules_disabled=len(snap.rules) - len(enabled), findings=findings,
                         limits=LIMITS[snap.provider] + LIMITS_COMMON, notes=snap.notes)


# ---------- one-line explanations (Nemotron Super) ----------

EXPLAIN_SYSTEM = (
    "You explain risky email settings to a non-technical office worker. For each finding, write ONE short, calm "
    "sentence on why an attacker would set this up. Use only the facts given. Reply with JSON only: "
    '{"items": [{"id": "...", "explanation": "..."}]}.'
)


class _Item(BaseModel):
    id: str
    explanation: str


class _ExplainOut(BaseModel):
    items: list[_Item] = []


async def explain_findings(report: MailboxReport) -> MailboxReport:
    if not report.findings:
        return report
    facts = "\n".join(f"- id={f.id}: {f.rule_name}: {'; '.join(f.reasons)}" for f in report.findings)
    out = await complete_json(
        step="mailbox_explain", key=f"{report.provider}:{report.source}", model=load_settings().model_super,
        messages=[{"role": "system", "content": EXPLAIN_SYSTEM}, {"role": "user", "content": facts}],
        schema=_ExplainOut, default=_ExplainOut(),
    )
    by_id = {i.id: i.explanation for i in out.items}
    return report.model_copy(update={"findings": [f.model_copy(update={"explanation": by_id.get(f.id)})
                                                  for f in report.findings]})
