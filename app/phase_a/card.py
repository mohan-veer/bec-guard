"""Result card. For now: the plain-English explanation (Nemotron Ultra, fallback Super), used only for
VERIFY_BEFORE_PAYING / LOOKS_UNUSUAL. The card layout itself is built in Phase 7.
"""
from pydantic import BaseModel

from app.clients.llm import complete_json
from app.config import load_settings
from app.phase_a.models import Decision, Signal

EXPLAIN_SYSTEM = (
    "You write for a busy accounts-payable clerk. In 2-3 short, calm sentences, explain why this email needs a "
    "check before acting, and say exactly what to do first. Use only the findings given. Never say the email is "
    '"safe" or "fraud". Reply with JSON only: {"summary": "..."}.'
)


class ExplainOut(BaseModel):
    summary: str | None = None


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
