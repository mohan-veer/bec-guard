"""Real Graph / Gmail API response shapes -> normalized Rule."""
from app.clients.mailbox import normalize_gmail, normalize_graph


def test_graph_rule_fields():
    rules = normalize_graph({"value": [{
        "id": "r1", "displayName": ".", "isEnabled": True,
        "conditions": {"bodyOrSubjectContains": ["invoice", "wire"], "senderContains": ["acme"]},
        "actions": {"moveToFolder": "F1", "markAsRead": True, "stopProcessingRules": True,
                    "forwardTo": [{"emailAddress": {"name": "X", "address": "X@Proton.me"}}],
                    "redirectTo": [{"emailAddress": {"address": "y@evil.com"}}]},
    }]}, folders={"F1": "RSS Feeds"})
    r = rules[0]
    assert (r.provider, r.id, r.name, r.enabled) == ("outlook", "r1", ".", True)
    assert r.keywords == ["invoice", "wire", "acme"]
    assert r.forward_to == ["x@proton.me", "y@evil.com"]
    assert r.move_to == "RSS Feeds" and r.mark_read and not r.delete


def test_graph_unknown_folder_keeps_id():
    r = normalize_graph({"value": [{"id": "r", "displayName": "n", "isEnabled": True, "conditions": {},
                                    "actions": {"moveToFolder": "AAMkXYZ"}}]}, folders={})[0]
    assert r.move_to == "AAMkXYZ" and not r.move_to_named


def test_gmail_filter_system_labels():
    rules, forwarding, auto = normalize_gmail(
        {"filter": [{"id": "f1", "criteria": {"query": 'invoice OR payment OR "bank details"', "from": "x@y.com"},
                     "action": {"addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX", "UNREAD"], "forward": "a@b.com"}}]},
        {"forwardingAddresses": [{"forwardingEmail": "a@b.com", "verificationStatus": "accepted"}]},
        {"enabled": True, "emailAddress": "a@b.com", "disposition": "trash"})
    r = rules[0]
    assert r.provider == "gmail" and r.enabled
    assert r.delete and r.mark_read and r.skips_inbox
    assert r.forward_to == ["a@b.com"]
    assert {"invoice", "payment", "bank details", "x@y.com"} <= set(r.keywords)
    assert "invoice" in r.name or "x@y.com" in r.name  # Gmail filters have no names; we describe them
    assert forwarding[0].email == "a@b.com" and forwarding[0].status == "accepted"
    assert auto.enabled and auto.disposition == "trash"


def test_gmail_empty_responses():
    rules, forwarding, auto = normalize_gmail({}, {}, {})
    assert rules == [] and forwarding == [] and not auto.enabled
