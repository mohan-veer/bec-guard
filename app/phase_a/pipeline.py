"""Phase A flow: parse -> Gate 0 -> entity/org/content checks in parallel -> scorer -> explanation."""
import asyncio

from app.phase_a.card import explain
from app.phase_a.content import (check_language, check_request_keywords, check_style, compare_to_ledger,
                                 extract_from_attachments, extract_payment_details, find_vendor, merge_details)
from app.phase_a.data import load_ledger, load_org
from app.phase_a.entity import FREE_EMAIL_DOMAINS, check_entity
from app.phase_a.intent import IntentOut, classify_intent
from app.phase_a.models import AnalysisResult, Decision, Email, Intent, Person, Signal
from app.phase_a.org import (callback_from_directory, check_domain_age, check_lookalike, check_web_consensus,
                             known_domains)
from app.phase_a.parse import parse_eml
from app.phase_a.scorer import score


def _internal_person(e: Email) -> Person | None:
    """The org member this email claims to be from (by address or display name)."""
    name = e.from_name.strip().lower()
    return next((p for p in load_org().people if p.email.lower() == e.from_addr or p.name.lower() == name), None)


async def run_entity(e: Email) -> list[Signal]:
    return check_entity(e, load_ledger(), load_org())


async def run_org(e: Email, gate: IntentOut) -> list[Signal]:
    ledger, org = load_ledger(), load_org()
    signals = [check_lookalike(e.from_domain, known_domains(ledger, org))]
    tasks = []
    if e.from_domain not in FREE_EMAIL_DOMAINS:
        tasks.append(check_domain_age(e.from_domain))

    person = _internal_person(e)
    vendor = find_vendor(e, ledger)
    company = vendor.name if vendor else gate.claimed_company
    if person:  # internal people: callback number only from our directory, never from the web
        signals.append(callback_from_directory(person))
    elif company and company.lower() != org.org_name.lower():
        tasks.append(check_web_consensus(company, e.from_domain, e.message_id, e.body_text, vendor))

    for result in await asyncio.gather(*tasks):
        signals += result if isinstance(result, list) else [result]
    return signals


async def run_content(e: Email) -> list[Signal]:
    vendor = find_vendor(e, load_ledger())
    language, style, attached = await asyncio.gather(check_language(e), check_style(e, vendor),
                                                     extract_from_attachments(e))
    signals = check_request_keywords(e.body_text) + language + style
    if vendor:
        signals += compare_to_ledger(merge_details(extract_payment_details(e.body_text), attached), vendor)
    return signals


async def analyze(e: Email) -> AnalysisResult:
    gate = await classify_intent(e)
    intent = gate.intent
    gate_sig = Signal(code="intent", group="gate", verdict="info", source="Nemotron Nano",
                      message=f"Request type: {intent.value.replace('_', ' ')}")
    if intent == Intent.NONE:
        return AnalysisResult(message_id=e.message_id, intent=intent, decision=None, rule=None, signals=[gate_sig])

    # All three groups always run; a passing group never skips another.
    groups = await asyncio.gather(run_entity(e), run_org(e, gate), run_content(e))
    signals = [gate_sig] + [s for g in groups for s in g]
    result = score(intent, signals)
    explanation = None
    if result.decision != Decision.NO_ISSUES_FOUND:
        explanation = await explain(result.decision, signals, e.message_id)
    return AnalysisResult(message_id=e.message_id, intent=intent, decision=result.decision, rule=result.rule,
                          signals=signals, explanation=explanation)


async def analyze_eml(raw: bytes) -> AnalysisResult:
    return await analyze(parse_eml(raw))
