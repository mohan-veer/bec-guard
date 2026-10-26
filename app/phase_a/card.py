"""Result card: required action first, then "looks fine" / "looks unusual" (one line each), plus the
plain-English explanation (Nemotron Ultra, fallback Super; only for VERIFY / UNUSUAL) and every check.
"""
from pydantic import BaseModel

from app.clients.llm import complete_json
from app.config import load_settings
from app.phase_a.models import AnalysisResult, Decision, Email, Signal

EXPLAIN_SYSTEM = (
    "You write for a busy accounts-payable clerk. In 2-3 short, calm sentences, explain why this email needs a "
    "check before acting, and say exactly what to do first. Use only the findings given. Never say the email is "
    '"safe" or "fraud". Reply with JSON only: {"summary": "..."}.'
)

HEADLINES = {
    Decision.VERIFY_BEFORE_PAYING: "Verify before paying",
    Decision.LOOKS_UNUSUAL: "Looks unusual",
    Decision.NO_ISSUES_FOUND: "No issues found",
    None: "No money or data request found",
}
_WEIGHT_ORDER = {"strong": 0, "medium": 1, "low": 2, "none": 3}


class ExplainOut(BaseModel):
    summary: str | None = None


class Card(BaseModel):
    message_id: str
    decision: Decision | None
    rule: str | None
    intent: str
    headline: str
    action: str
    explanation: str | None
    looks_fine: list[str]
    looks_unusual: list[str]
    callback: dict | None
    checks: list[Signal]          # the "How this was checked" panel


async def explain(decision: Decision, signals: list[Signal], key: str) -> str | None:
    # Only our own findings go to the model, never the raw email, so text in the email can't steer the wording.
    findings = "\n".join(f"- {s.message}" for s in signals if s.verdict == "unusual" or s.code == "callback_number")
    s = load_settings()
    out = await complete_json(
        step="explain", key=key, model=s.model_ultra, fallback_model=s.model_super,
        messages=[{"role": "system", "content": EXPLAIN_SYSTEM},
                  {"role": "user", "content": f"Decision: {decision.value}\nFindings:\n{findings}"}],
        schema=ExplainOut, default=ExplainOut(),
    )
    return out.summary


def _call_phrase(callback: dict | None) -> str:
    if not callback:
        return "confirm using a phone number you already have on file, not one from this email"
    return f"call {callback['name']} at {callback['phone']} (number from {callback['from']}, not from this email)"


def _action(r: AnalysisResult, e: Email, callback: dict | None) -> str:
    call = _call_phrase(callback)
    looks_like = next((s.data.get("looks_like") for s in r.signals if s.code == "lookalike_domain"), None)
    impersonated = next((s.data for s in r.signals if s.code == "address_lookalike"), {})
    templates = {
        "bank_change": f"Bank details changed. Before paying, {call} and confirm the new account.",
        "lookalike_domain": f"This email is not from {looks_like}. Before acting on it, {call}.",
        "address_lookalike": f"This email isn't from {impersonated.get('owner')}'s address on file "
                             f"({impersonated.get('looks_like')}). Before acting on it, {call}.",
        "known_name_new_address": f"{e.from_name} is writing from an address that isn't on file. Before acting, {call}.",
        "gift_cards": f"Gift card request. Before buying anything, {call} and confirm.",
        "sensitive_data": f"Request for employee records. Before sending anything, {call} and confirm.",
        "any_strong_signal": f"Something important looks unusual. Before acting, {call} and confirm.",
        "two_medium_signals": f"A few things look unusual. Before paying, {call} and confirm the request.",
        "default": "No issues found in the checks below.",
    }
    return templates.get(r.rule or "", "No money or data request found.")


def build_card(r: AnalysisResult, e: Email) -> Card:
    callback = next((s.data for s in r.signals if s.code == "callback_number"), None)
    unusual = sorted((s for s in r.signals if s.verdict == "unusual"), key=lambda s: _WEIGHT_ORDER[s.weight])
    return Card(
        message_id=r.message_id, decision=r.decision, rule=r.rule, intent=r.intent.value,
        headline=HEADLINES[r.decision], action=_action(r, e, callback), explanation=r.explanation,
        looks_fine=[s.message for s in r.signals if s.verdict == "fine"],
        looks_unusual=[s.message for s in unusual],
        callback=callback, checks=r.signals,
    )
