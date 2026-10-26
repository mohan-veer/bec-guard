"""Deterministic decision. No LLM decides: LLMs only produce signals, this table decides.

Rules are checked top to bottom; the first match wins.
"""
from app.phase_a.models import Decision, Intent, ScoreResult, Signal

V, U, N = Decision.VERIFY_BEFORE_PAYING, Decision.LOOKS_UNUSUAL, Decision.NO_ISSUES_FOUND


def _fired(signals: list[Signal]) -> set[str]:
    return {s.code for s in signals if s.verdict == "unusual"}


def _medium_count(signals: list[Signal]) -> int:
    return sum(1 for s in signals if s.verdict == "unusual" and s.weight == "medium")


def _any_strong(signals: list[Signal]) -> bool:
    return any(s.verdict == "unusual" and s.weight == "strong" for s in signals)


#  (rule name,               condition(intent, signals),                                                  decision)
RULES = [
    ("bank_change",            lambda i, s: "bank_change" in _fired(s) or i in (Intent.BANK_CHANGE, Intent.PAYROLL_CHANGE), V),
    ("lookalike_domain",       lambda i, s: "lookalike_domain" in _fired(s),                                 V),
    ("known_name_new_address", lambda i, s: "known_name_new_address" in _fired(s) and i != Intent.NONE,      V),
    ("gift_cards",             lambda i, s: i == Intent.GIFT_CARDS or "gift_card_request" in _fired(s),      V),
    ("sensitive_data",         lambda i, s: "sensitive_data_request" in _fired(s),                           V),
    ("any_strong_signal",      lambda i, s: _any_strong(s),                                                  V),
    ("two_medium_signals",     lambda i, s: _medium_count(s) >= 2,                                           U),
    ("default",                lambda i, s: True,                                                            N),
]


def score(intent: Intent, signals: list[Signal]) -> ScoreResult:
    for name, condition, decision in RULES:
        if condition(intent, signals):
            return ScoreResult(decision=decision, rule=name)
    raise AssertionError("unreachable: 'default' always matches")
