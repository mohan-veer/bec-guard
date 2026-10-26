"""Phase A flow: parse -> Gate 0 -> entity/org/content checks in parallel -> scorer -> explanation.

analyze_events() streams progress so the UI can fail fast: as soon as the signals so far already decide
VERIFY_BEFORE_PAYING it emits an "early" event. VERIFY can't be downgraded by more signals (rules only look for
the presence of signals), so the early warning is always the final decision.
"""
import asyncio
from collections.abc import AsyncIterator

from app.phase_a.card import explain
from app.phase_a.content import (check_language, check_request_keywords, check_style, compare_to_ledger,
                                 extract_from_attachments, extract_payment_details, find_vendor, merge_details)
from app.phase_a.data import load_ledger, load_org
from app.phase_a.entity import FREE_EMAIL_DOMAINS, check_entity
from app.phase_a.intent import IntentOut, classify_intent
from app.phase_a.models import AnalysisResult, Decision, Email, Intent, Person, Signal
from app.phase_a.org import (callback_from_directory, callback_signal, check_domain_age, check_lookalike,
                             check_web_consensus, known_domains)
from app.phase_a.parse import parse_eml
from app.phase_a.scorer import score


# When VERIFY is reached from Gate 0's intent alone, before any strong signal exists.
EARLY_REASONS = {
    "bank_change": "This email asks to change bank or payment details.",
    "gift_cards": "This email asks for gift cards.",
}


def _internal_person(e: Email) -> Person | None:
    """The org member this email claims to be from (by address or display name)."""
    name = e.from_name.strip().lower()
    return next((p for p in load_org().people if p.email.lower() == e.from_addr or p.name.lower() == name), None)


async def run_entity(e: Email) -> list[Signal]:
    return check_entity(e, load_ledger(), load_org())


async def run_lookalike(e: Email) -> list[Signal]:
    return [check_lookalike(e.from_domain, known_domains(load_ledger(), load_org()), display=e.from_domain_raw)]


async def run_org(e: Email, gate: IntentOut) -> list[Signal]:
    """Slow org checks: domain age (RDAP) and web consensus / callback number (agent + Tavily)."""
    ledger, org = load_ledger(), load_org()
    signals: list[Signal] = []
    tasks = []
    if e.from_domain not in FREE_EMAIL_DOMAINS:
        tasks.append(check_domain_age(e.from_domain))

    person = _internal_person(e)
    vendor = find_vendor(e, ledger)
    company = vendor.name if vendor else gate.claimed_company
    if person:  # internal people: callback number only from our directory, never from the web
        signals.append(callback_from_directory(person))
    elif vendor and not vendor.official_website:  # no website on file: the number in our vendor records is the source
        signals.append(callback_signal(vendor.name, vendor.official_phone, "your vendor records", "vendor ledger"))
    elif company and company.lower() != org.org_name.lower():
        on_file = vendor is not None and any(c.email.lower() == e.from_addr for c in vendor.contacts)
        tasks.append(check_web_consensus(company, e.from_domain, e.message_id, e.body_text, vendor, on_file))

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


async def analyze_events(e: Email) -> AsyncIterator[dict]:
    """Yields {"type": "gate" | "signals" | "early" | "result", ...}; the last event carries the AnalysisResult."""
    gate = await classify_intent(e)
    intent = gate.intent
    gate_sig = Signal(code="intent", group="gate", verdict="info", source="Nemotron Nano",
                      message=f"Request type: {intent.value.replace('_', ' ')}")
    yield {"type": "gate", "intent": intent.value, "claimed_company": gate.claimed_company}
    if intent == Intent.NONE:
        yield {"type": "result", "result": AnalysisResult(message_id=e.message_id, intent=intent, decision=None,
                                                          rule=None, signals=[gate_sig])}
        return

    # All groups always run; a passing group never skips another.
    pending = {asyncio.create_task(run_entity(e)): "entity", asyncio.create_task(run_lookalike(e)): "org",
               asyncio.create_task(run_org(e, gate)): "org", asyncio.create_task(run_content(e)): "content"}
    signals, warned = [gate_sig], False
    while pending:
        done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            group = pending.pop(task)
            new = task.result()
            signals += new
            yield {"type": "signals", "group": group, "signals": new}
        if pending and not warned:
            partial = score(intent, signals)
            if partial.decision == Decision.VERIFY_BEFORE_PAYING:
                warned = True
                strongest = next((s.message for s in signals if s.verdict == "unusual" and s.weight == "strong"),
                                 EARLY_REASONS.get(partial.rule, "Something in this email needs checking."))
                yield {"type": "early", "decision": partial.decision.value, "reason": strongest}

    result = score(intent, signals)
    explanation = None
    if result.decision != Decision.NO_ISSUES_FOUND:
        explanation = await explain(result.decision, signals, e.message_id)
    yield {"type": "result", "result": AnalysisResult(message_id=e.message_id, intent=intent, decision=result.decision,
                                                      rule=result.rule, signals=signals, explanation=explanation)}


async def analyze(e: Email) -> AnalysisResult:
    async for event in analyze_events(e):
        if event["type"] == "result":
            return event["result"]
    raise AssertionError("analyze_events always ends with a result")


async def analyze_eml(raw: bytes) -> AnalysisResult:
    return await analyze(parse_eml(raw))
