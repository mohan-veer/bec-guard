"""Mailbox rules and forwarding settings, normalized from the providers' own API shapes.

Payloads come from the mail-side integration (Gmail Apps Script today; a Microsoft Graph client later) or from the
sample fixtures. Gmail: users.settings.filters / forwardingAddresses / autoForwarding. Graph: inbox messageRules
(moveToFolder is a folder ID; names are passed in separately).
"""
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "mailbox"

Provider = Literal["outlook", "gmail"]


class Rule(BaseModel):
    provider: Provider
    id: str
    name: str
    enabled: bool
    keywords: list[str] = []      # condition strings (subject/body/sender words, query terms)
    forward_to: list[str] = []    # forward, redirect, forward-as-attachment (lowercased)
    delete: bool = False
    mark_read: bool = False
    move_to: str | None = None    # folder name, or the raw folder ID if it couldn't be resolved
    move_to_named: bool = False
    skips_inbox: bool = False     # Gmail: removes INBOX (archive)


class ForwardingAddress(BaseModel):
    email: str
    status: str


class AutoForward(BaseModel):
    enabled: bool = False
    email: str | None = None
    disposition: str | None = None


class MailboxSnapshot(BaseModel):
    provider: Provider
    source: Literal["fixture", "live"]
    rules: list[Rule]
    forwarding: list[ForwardingAddress] = []
    auto_forward: AutoForward = AutoForward()
    notes: list[str] = []


# ---------- normalizers (pure; shared by fixture and live mode) ----------

def _addresses(recipients: list[dict] | None) -> list[str]:
    return [r["emailAddress"]["address"].lower() for r in recipients or [] if r.get("emailAddress", {}).get("address")]


def normalize_graph(payload: dict, folders: dict[str, str]) -> list[Rule]:
    rules = []
    for r in payload.get("value", []):
        c, a = r.get("conditions") or {}, r.get("actions") or {}
        words = [w for k in ("bodyContains", "bodyOrSubjectContains", "subjectContains", "senderContains",
                             "recipientContains", "headerContains") for w in c.get(k) or []]
        words += _addresses(c.get("fromAddresses"))
        folder_id = a.get("moveToFolder")
        rules.append(Rule(
            provider="outlook", id=r["id"], name=r.get("displayName") or "", enabled=bool(r.get("isEnabled")),
            keywords=words,
            forward_to=_addresses(a.get("forwardTo")) + _addresses(a.get("redirectTo")) +
                       _addresses(a.get("forwardAsAttachmentTo")),
            delete=bool(a.get("delete") or a.get("permanentDelete")), mark_read=bool(a.get("markAsRead")),
            move_to=folders.get(folder_id, folder_id) if folder_id else None, move_to_named=folder_id in folders,
        ))
    return rules


_QUERY_TERM = re.compile(r'"([^"]+)"|([^\s()"]+)')


def _query_terms(query: str) -> list[str]:
    terms = [q or w for q, w in _QUERY_TERM.findall(query or "")]
    return [t for t in terms if t.upper() not in {"OR", "AND"} and t != "-"]


def normalize_gmail(filters: dict, forwarding: dict, auto: dict) -> tuple[list[Rule], list[ForwardingAddress], AutoForward]:
    rules = []
    for f in filters.get("filter", []):
        crit, act = f.get("criteria") or {}, f.get("action") or {}
        words = [crit[k] for k in ("from", "to", "subject") if crit.get(k)] + _query_terms(crit.get("query", ""))
        add, remove = set(act.get("addLabelIds") or []), set(act.get("removeLabelIds") or [])
        described = [f"from {crit['from']}" if crit.get("from") else "", f"matching {crit['query']}" if crit.get("query") else "",
                     f"subject {crit['subject']}" if crit.get("subject") else ""]
        rules.append(Rule(
            provider="gmail", id=f["id"], name=("Filter · " + " · ".join(d for d in described if d))[:120],
            enabled=True,  # Gmail filters have no on/off switch
            keywords=words, forward_to=[act["forward"].lower()] if act.get("forward") else [],
            delete="TRASH" in add, mark_read="UNREAD" in remove, skips_inbox="INBOX" in remove,
            move_to=None,
        ))
    addresses = [ForwardingAddress(email=a["forwardingEmail"].lower(), status=a.get("verificationStatus", ""))
                 for a in forwarding.get("forwardingAddresses", [])]
    auto_fwd = AutoForward(enabled=bool(auto.get("enabled")), email=(auto.get("emailAddress") or "").lower() or None,
                           disposition=auto.get("disposition"))
    return rules, addresses, auto_fwd


# ---------- fixture mode ----------

def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def read_fixture(provider: Provider) -> MailboxSnapshot:
    if provider == "outlook":
        folders = {f["id"]: f["displayName"] for f in _fixture("outlook_folders.json")["value"]}
        return MailboxSnapshot(provider="outlook", source="fixture",
                               rules=normalize_graph(_fixture("outlook_rules.json"), folders))
    rules, fwd, auto = normalize_gmail(_fixture("gmail_filters.json"), _fixture("gmail_forwarding.json"),
                                       _fixture("gmail_autoforwarding.json"))
    return MailboxSnapshot(provider="gmail", source="fixture", rules=rules, forwarding=fwd, auto_forward=auto)
