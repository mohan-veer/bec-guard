"""Phase A flow: parse -> Gate 0 -> entity/org/content checks in parallel -> scorer."""
import asyncio

from app.phase_a.content import check_request_keywords, compare_to_ledger, extract_payment_details, find_vendor
from app.phase_a.data import load_ledger, load_org
from app.phase_a.entity import check_entity
from app.phase_a.intent import classify_intent
from app.phase_a.models import AnalysisResult, Email, Intent, Signal
from app.phase_a.org import check_lookalike, known_domains
from app.phase_a.parse import parse_eml
from app.phase_a.scorer import score


async def run_entity(e: Email) -> list[Signal]:
    return check_entity(e, load_ledger(), load_org())


async def run_org(e: Email) -> list[Signal]:
    return [check_lookalike(e.from_domain, known_domains(load_ledger(), load_org()))]


async def run_content(e: Email) -> list[Signal]:
    signals = check_request_keywords(e.body_text)
    vendor = find_vendor(e, load_ledger())
    if vendor:
        signals += compare_to_ledger(extract_payment_details(e.body_text), vendor)
    return signals


async def analyze(e: Email) -> AnalysisResult:
    intent = await classify_intent(e)
    gate = Signal(code="intent", group="gate", verdict="info", message=f"Request type: {intent.value.replace('_', ' ')}",
                  source="Nemotron Nano")
    if intent == Intent.NONE:
        return AnalysisResult(message_id=e.message_id, intent=intent, decision=None, rule=None, signals=[gate])

    # All three groups always run; a passing group never skips another.
    groups = await asyncio.gather(run_entity(e), run_org(e), run_content(e))
    signals = [gate] + [s for g in groups for s in g]
    result = score(intent, signals)
    return AnalysisResult(message_id=e.message_id, intent=intent, decision=result.decision, rule=result.rule,
                          signals=signals)


async def analyze_eml(raw: bytes) -> AnalysisResult:
    return await analyze(parse_eml(raw))
