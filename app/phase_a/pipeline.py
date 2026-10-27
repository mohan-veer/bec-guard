"""Phase A flow: parse -> Gate 0 -> entity/org/content checks in parallel -> scorer -> explanation.

analyze_events() streams progress so the UI can fail fast: as soon as the signals so far already decide
VERIFY_BEFORE_PAYING it emits an "early" event. VERIFY can't be downgraded by more signals (rules only look for
the presence of signals), so the early warning is always the final decision.
"""
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.phase_a.card import word_signals
from app.phase_a.content import (check_language, check_request_keywords, check_style, compare_to_ledger,
                                 extract_from_attachments, extract_payment_details, find_vendor_match, merge_details,
                                 same_company, vendor_by_name)
from app.phase_a.data import load_ledger, load_org
from app.phase_a.entity import FREE_EMAIL_DOMAINS, check_entity
from app.phase_a.intent import IntentOut, classify_intent
from app.phase_a.models import AnalysisResult, Decision, Email, Intent, Person, Signal, Vendor
from app.phase_a.org import (callback_from_directory, check_domain_age, check_email_phones, check_lookalike,
                             check_web_consensus, known_domains, records_callback)
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


@dataclass
class Subject:
    """Who the email is about, decided once and shared by every check."""
    vendor: Vendor | None        # vendor whose records apply (payment comparison, records phone, style history)
    how: str | None              # address | domain | lookalike | name | claimed
    company: str | None          # company to verify on the web when the email isn't from a known contact
    resembles: Vendor | None     # vendor whose contact the address imitates, when the email claims another company


def resolve_subject(e: Email, gate: IntentOut) -> Subject:
    ledger, org = load_ledger(), load_org()
    vendor, how = find_vendor_match(e, ledger)
    claimed = gate.claimed_company if not same_company(gate.claimed_company, org.org_name) else None
    # The company the email CLAIMS beats a vendor its address or display name merely resembles.
    if vendor and how in ("lookalike", "name") and claimed and not same_company(claimed, vendor.name):
        named = vendor_by_name(ledger, claimed)
        return Subject(vendor=named, how="claimed" if named else None, company=claimed, resembles=vendor)
    if not vendor and claimed:
        named = vendor_by_name(ledger, claimed)
        if named:
            return Subject(vendor=named, how="claimed", company=named.name, resembles=None)
    return Subject(vendor=vendor, how=how, company=vendor.name if vendor else claimed, resembles=None)


async def run_entity(e: Email, subject: Subject) -> list[Signal]:
    signals = check_entity(e, load_ledger(), load_org())
    if subject.resembles:  # the address resembling another vendor's contact is a supporting fact, not the headline
        signals = [s.model_copy(update={
            "weight": "medium",
            "message": f"Not the address your vendor {s.data['owner']} ({subject.resembles.name}) usually writes from: "
                       f"usually {s.data['looks_like']}, this time {e.from_addr_raw or e.from_addr}"})
            if s.code == "address_lookalike" else s for s in signals]
    return signals


async def run_lookalike(e: Email) -> list[Signal]:
    s = check_lookalike(e.from_domain, known_domains(load_ledger(), load_org()), display=e.from_domain_raw)
    # "outlook.com doesn't imitate a company you work with" tells the reader nothing: hide the all-clear for free services
    return [] if s.verdict == "fine" and e.from_domain in FREE_EMAIL_DOMAINS else [s]


async def run_org(e: Email, subject: Subject) -> list[Signal]:
    """Slow org checks: domain age (RDAP), official website / phone (Super agent + Tavily), phone cross-checks."""
    signals: list[Signal] = []
    tasks = []
    if e.from_domain not in FREE_EMAIL_DOMAINS:
        tasks.append(check_domain_age(e.from_domain))

    person = _internal_person(e)
    vendor = subject.vendor
    if person:  # internal people: callback number only from our directory, never from the web
        signals.append(callback_from_directory(person))
    else:
        if vendor:  # the vendor records are the first number to call
            signals.append(records_callback(vendor))
            paid = sum(1 for i in vendor.past_invoices if i.status == "paid")
            signals.append(Signal(code="vendor_on_file", group="org", verdict="fine", source="vendor ledger",
                                  message=f"{vendor.name} is one of your vendors ({paid} paid invoices on record)"))
        elif subject.company:
            signals.append(Signal(code="not_a_vendor", group="org", verdict="unusual", weight="low", source="vendor ledger",
                                  message=f"{subject.company} isn't one of your vendors (no invoices on record)"))
        # Web check: an unknown company the email claims, or a vendor on file whose website we know (cross-check).
        # A vendor on file without a website isn't searched: the web's "Acme Supply" may be a different company.
        if subject.company and (vendor is None or vendor.official_website):
            on_file = vendor is not None and subject.how == "address"
            tasks.append(check_web_consensus(subject.company, e.from_domain, e.message_id, e.body_text, vendor, on_file))

    for result in await asyncio.gather(*tasks):
        signals += result if isinstance(result, list) else [result]
    signals += check_email_phones(e.body_text, [s for s in signals if s.code == "callback_number"])
    return signals


async def run_content(e: Email, subject: Subject) -> list[Signal]:
    vendor = subject.vendor
    language, style, attached = await asyncio.gather(check_language(e), check_style(e, vendor),
                                                     extract_from_attachments(e))
    signals = check_request_keywords(e.body_text) + language + style
    details = merge_details(extract_payment_details(e.body_text), attached)
    if vendor:
        signals += compare_to_ledger(details, vendor)
    elif details.account_last4 or details.routing_number:  # paying someone we have no relationship with
        where = f" in {details.found_in}" if details.found_in else ""
        last4 = f" (account ending {details.account_last4})" if details.account_last4 else ""
        signals.append(Signal(code="new_payee_account", group="content", verdict="unusual", weight="medium",
                              source="rules (ledger)",
                              message=f"Asks for payment to a bank account you have no record of{last4}{where}"))
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
    subject = resolve_subject(e, gate)
    pending = {asyncio.create_task(run_entity(e, subject)): "entity", asyncio.create_task(run_lookalike(e)): "org",
               asyncio.create_task(run_org(e, subject)): "org", asyncio.create_task(run_content(e, subject)): "content"}
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
    wording = {}
    if result.decision != Decision.NO_ISSUES_FOUND:  # plain-language card lines (Nemotron Ultra), for warnings only
        wording = await word_signals(signals, e.message_id)
    yield {"type": "result", "result": AnalysisResult(message_id=e.message_id, intent=intent, decision=result.decision,
                                                      rule=result.rule, signals=signals, wording=wording)}


async def analyze(e: Email) -> AnalysisResult:
    async for event in analyze_events(e):
        if event["type"] == "result":
            return event["result"]
    raise AssertionError("analyze_events always ends with a result")


async def analyze_eml(raw: bytes) -> AnalysisResult:
    return await analyze(parse_eml(raw))
