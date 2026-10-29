import pytest

from app.phase_a.models import Decision, Intent, Signal
from app.phase_a.scorer import score

V, U, N = Decision.VERIFY_BEFORE_PAYING, Decision.LOOKS_UNUSUAL, Decision.NO_ISSUES_FOUND


def sig(code, weight="medium", verdict="unusual"):
    return Signal(code=code, group="content", verdict=verdict, weight=weight, message=code, source="test")


@pytest.mark.parametrize("intent,signals,decision,rule", [
    # bank change always wins, even if everything else is fine
    (Intent.PAYMENT_REQUEST, [sig("bank_change", "strong"), sig("known_sender", verdict="fine")], V, "bank_change"),
    (Intent.BANK_CHANGE, [], V, "bank_change"),
    (Intent.PAYROLL_CHANGE, [], V, "bank_change"),
    (Intent.PAYMENT_REQUEST, [sig("lookalike_domain", "strong")], V, "lookalike_domain"),
    (Intent.PAYMENT_REQUEST, [sig("known_name_new_address", "strong")], V, "known_name_new_address"),
    (Intent.GIFT_CARDS, [], V, "gift_cards"),
    (Intent.PAYMENT_REQUEST, [sig("gift_card_request", "strong")], V, "gift_cards"),
    (Intent.DATA_REQUEST, [sig("sensitive_data_request", "strong")], V, "sensitive_data"),
    (Intent.PAYMENT_REQUEST, [sig("something_new", "strong")], V, "any_strong_signal"),
    (Intent.PAYMENT_REQUEST, [sig("dmarc_fail"), sig("reply_to_mismatch")], U, "two_medium_signals"),
    (Intent.PAYMENT_REQUEST, [sig("dmarc_fail")], N, "default"),
    (Intent.PAYMENT_REQUEST, [sig("first_contact", "low"), sig("no_dmarc", "low"), sig("po_missing", "low")], N, "default"),
    (Intent.PAYMENT_REQUEST, [sig("dmarc_fail"), sig("reply_to_mismatch", verdict="fine")], N, "default"),
    (Intent.DATA_REQUEST, [], N, "default"),  # a data request that isn't W-2/employee records
    # prevention first: paying an account with no record is always verified, even when nothing else is wrong
    (Intent.PAYMENT_REQUEST, [sig("new_payee_account")], V, "new_payee"),
    (Intent.PAYMENT_REQUEST, [sig("new_payee_account"), sig("known_sender", verdict="fine")], V, "new_payee"),
    (Intent.PAYMENT_REQUEST, [sig("new_payee_account", verdict="fine")], N, "default"),
    # impersonation still names the headline when it is also present
    (Intent.PAYMENT_REQUEST, [sig("new_payee_account"), sig("lookalike_domain", "strong")], V, "lookalike_domain"),
])
def test_rules(intent, signals, decision, rule):
    r = score(intent, signals)
    assert (r.decision, r.rule) == (decision, rule)


def test_impersonation_outranks_bank_change():
    # Who is really writing is the headline; the new bank account is mentioned in the same action line.
    for code in ("lookalike_domain", "address_lookalike", "known_name_new_address"):
        assert score(Intent.PAYMENT_REQUEST, [sig(code, "strong"), sig("bank_change", "strong")]).rule == code


def test_bank_change_from_a_trusted_sender_stays_bank_change():
    assert score(Intent.GIFT_CARDS, [sig("bank_change", "strong")]).rule == "bank_change"


def test_address_lookalike_rule():
    r = score(Intent.PAYMENT_REQUEST, [sig("address_lookalike", "strong")])
    assert (r.decision, r.rule) == (V, "address_lookalike")
