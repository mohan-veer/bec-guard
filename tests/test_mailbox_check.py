import pytest

from app.clients.mailbox import AutoForward, ForwardingAddress, MailboxSnapshot, Rule
from app.phase_b.mailbox_check import check_mailbox

ORG = ["riverbenddental.com"]


def rule(**kw):
    base = dict(provider="outlook", id="r", name="My rule", enabled=True)
    return Rule(**{**base, **kw})


def run(*rules, forwarding=(), auto=None):
    snap = MailboxSnapshot(provider="outlook", source="fixture", rules=list(rules), forwarding=list(forwarding),
                           auto_forward=auto or AutoForward())
    return check_mailbox(snap, ORG)


def test_external_forward_is_high():
    f = run(rule(forward_to=["me.backup@protonmail.com"])).findings[0]
    assert f.severity == "high"
    assert any("outside address" in r and "protonmail.com" in r for r in f.reasons)
    assert "password" in f.next_step and "sign out" in f.next_step


def test_internal_forward_is_not_flagged():
    assert run(rule(forward_to=["priya.raman@riverbenddental.com"])).findings == []


def test_hide_plus_payment_keywords_is_high():
    f = run(rule(name="Invoices", keywords=["invoice", "wire"], move_to="RSS Feeds", move_to_named=True, mark_read=True)).findings[0]
    assert f.severity == "high"
    assert any("payment words" in r for r in f.reasons)
    assert any("RSS Feeds" in r for r in f.reasons)
    assert any("marks" in r.lower() and "read" in r.lower() for r in f.reasons)


@pytest.mark.parametrize("name", [".", "..", "...", " ", "-", "a"])
def test_meaningless_name_plus_hiding_is_high(name):
    f = run(rule(name=name, delete=True)).findings[0]
    assert f.severity == "high"
    assert any("meaningless name" in r for r in f.reasons)


def test_delete_alone_is_review():
    f = run(rule(name="Remove spam", keywords=["enter to win"], delete=True)).findings[0]
    assert f.severity == "review"


def test_obscure_folder_alone_is_review():
    assert run(rule(move_to="Conversation History", move_to_named=True)).findings[0].severity == "review"


def test_normal_folder_and_skip_inbox_alone_are_not_flagged():
    assert run(rule(name="Newsletters", keywords=["newsletter"], move_to="Newsletters", move_to_named=True)).findings == []
    assert run(rule(provider="gmail", name="news", skips_inbox=True)).findings == []


def test_unresolved_folder_id_with_keywords_is_still_high():
    f = run(rule(keywords=["payment"], move_to="AAMkXYZ", move_to_named=False)).findings[0]
    assert f.severity == "high"
    assert any("a folder" in r for r in f.reasons)


def test_disabled_rules_are_skipped_but_counted():
    r = run(rule(forward_to=["x@evil.com"], enabled=False))
    assert r.findings == [] and r.rules_disabled == 1 and r.rules_checked == 1


def test_gmail_forwarding_addresses_and_auto_forward():
    r = run(forwarding=[ForwardingAddress(email="x@gmail.com", status="accepted"),
                        ForwardingAddress(email="y@gmail.com", status="pending"),
                        ForwardingAddress(email="ap@riverbenddental.com", status="accepted")],
            auto=AutoForward(enabled=True, email="x@gmail.com", disposition="trash"))
    sev = {f.rule_name: f.severity for f in r.findings}
    assert sev["Forwarding address x@gmail.com"] == "high"
    assert sev["Forwarding address y@gmail.com"] == "review"
    assert "Forwarding address ap@riverbenddental.com" not in sev
    auto = next(f for f in r.findings if f.rule_name == "Automatic forwarding")
    assert auto.severity == "high" and any("deleted" in x for x in auto.reasons)


def test_findings_sorted_high_first_and_limits_listed():
    r = run(rule(id="a", name="Remove spam", delete=True), rule(id="b", forward_to=["x@evil.com"]))
    assert [f.severity for f in r.findings] == ["high", "review"]
    assert any("Entra ID P1" in lim for lim in r.limits)
