"""Entity checks: who is the sender, and do the headers back that up? Rules only."""
import re

from app.phase_a.models import Email, OrgDirectory, Signal, VendorLedger
from app.phase_a.org import edit_distance

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "ymail.com", "aol.com", "icloud.com", "me.com", "proton.me", "protonmail.com",
    "gmx.com", "mail.com", "zoho.com",
}


def _sig(code, verdict, message, weight="none") -> Signal:
    return Signal(code=code, group="entity", verdict=verdict, weight=weight, message=message, source="rules")


def _known_identities(ledger: VendorLedger, org: OrgDirectory) -> dict[str, set[str]]:
    """Lowercased name -> addresses on file for it (people, vendor contacts, vendor names)."""
    names: dict[str, set[str]] = {}
    for p in org.people:
        names.setdefault(p.name.lower(), set()).add(p.email.lower())
    for v in ledger.vendors:
        names.setdefault(v.name.lower(), set()).update(c.email.lower() for c in v.contacts)
        for c in v.contacts:
            names.setdefault(c.name.lower(), set()).add(c.email.lower())
    return names


def _known_sender_label(addr: str, ledger: VendorLedger, org: OrgDirectory) -> str | None:
    for p in org.people:
        if p.email.lower() == addr:
            return f"Writes from {p.name}'s address in your staff directory"
    for v in ledger.vendors:
        for c in v.contacts:
            if c.email.lower() == addr:
                return f"Writes from the address you have on file for {c.name} at {v.name}"
    return None


MIN_LOOKALIKE_USERNAME = 6  # shorter usernames ("ar", "info") collide too easily; arbitrary


def lookalike_of(addr: str, on_file: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Free-provider impersonation: the same username on another provider, or a username 1–2 characters off
    (dots ignored), where either side is a free provider. Corporate domains are covered by the domain lookalike check.
    on_file: (owner name, address) pairs. Returns the (owner, real address) being imitated."""
    local, domain = addr.rsplit("@", 1)
    for owner, real in on_file:
        real = real.lower()
        real_local, real_domain = real.rsplit("@", 1)
        if real == addr or FREE_EMAIL_DOMAINS.isdisjoint({domain, real_domain}):
            continue
        a, b = local.replace(".", ""), real_local.replace(".", "")
        if len(b) >= MIN_LOOKALIKE_USERNAME and (a == b or edit_distance(a, b) <= 2):
            return owner, real
    return None


def _address_lookalike(addr: str, ledger: VendorLedger, org: OrgDirectory) -> tuple[str, str] | None:
    on_file = [(p.name, p.email) for p in org.people] + \
              [(c.name if c.name else v.name, c.email) for v in ledger.vendors for c in v.contacts]
    return lookalike_of(addr, on_file)


PROVIDER_NAMES = {"gmail.com": "Gmail", "googlemail.com": "Gmail", "outlook.com": "Outlook", "hotmail.com": "Hotmail",
                  "live.com": "Outlook", "msn.com": "MSN", "yahoo.com": "Yahoo", "ymail.com": "Yahoo", "aol.com": "AOL",
                  "icloud.com": "iCloud", "me.com": "iCloud", "proton.me": "Proton", "protonmail.com": "Proton",
                  "gmx.com": "GMX", "mail.com": "Mail.com", "zoho.com": "Zoho"}


def _name_in_address(name: str, local: str) -> bool:
    """Does the address's user part contain any word of the display name? ("Sam Ortiz" / sam.ortiz@ -> yes)"""
    compact = re.sub(r"[^a-z0-9]", "", local.lower())
    return any(len(w) >= 3 and w in compact for w in re.findall(r"[a-z0-9]+", name.lower()))


def check_entity(e: Email, ledger: VendorLedger, org: OrgDirectory) -> list[Signal]:
    """Who sent it. Wording is for non-technical readers: plain words, show the actual addresses, no jargon."""
    out: list[Signal] = []
    addr, domain = e.from_addr, e.from_domain
    shown = e.from_addr_raw or addr

    known = _known_sender_label(addr, ledger, org)
    if known:
        out.append(_sig("known_sender", "fine", known))
    else:
        on_file = _known_identities(ledger, org).get(e.from_name.strip().lower())
        if on_file:
            out.append(Signal(code="known_name_new_address", group="entity", verdict="unusual", weight="strong",
                              source="rules", data={"on_file": sorted(on_file)[0]},
                              message=f'Uses the name "{e.from_name}", but writes from {shown}, not the address you '
                                      f"have on file ({sorted(on_file)[0]})"))
        elif e.from_name.strip() and not _name_in_address(e.from_name, addr.rsplit("@", 1)[0]):
            out.append(_sig("display_name_mismatch", "unusual", f'Signs as "{e.from_name.strip()}", but writes from {shown}',
                            "low"))
        lookalike = _address_lookalike(addr, ledger, org)
        if lookalike:
            owner, real = lookalike
            out.append(Signal(code="address_lookalike", group="entity", verdict="unusual", weight="strong", source="rules",
                              message=f"Not the address {owner} usually writes from: usually {real}, this time {shown}",
                              data={"looks_like": real, "owner": owner}))
        # A known contact on a free provider is normal (small vendors often are); only unknown senders are flagged.
        if domain in FREE_EMAIL_DOMAINS:
            out.append(_sig("free_email", "unusual",
                            f"Sent from a free {PROVIDER_NAMES.get(domain, domain)} address ({domain}), not a company email",
                            "medium"))
        out.append(_sig("first_contact", "unusual",
                        "Not in your vendor records or staff directory. New contacts happen, but check them first.", "low"))

    if e.dmarc == "fail":
        out.append(_sig("dmarc_fail", "unusual", f"{domain} could not confirm that this email really came from it",
                        "medium"))
    elif e.dmarc in (None, "none"):
        out.append(_sig("no_dmarc", "unusual", f"{domain} doesn't use the standard protection against forged emails",
                        "low"))
    elif e.spf == "pass" and e.dkim == "pass" and e.dmarc == "pass":
        if known:  # the address is on file and its mail service confirms the email really came from that address
            out.append(_sig("email_auth_pass", "fine", f"Confirmed as sent from {shown}"))
        elif domain not in FREE_EMAIL_DOMAINS:  # for free providers the line above already says where it came from
            out.append(_sig("email_auth_unverified_sender", "info",
                            f"Came from {domain}; that alone doesn't tell us who wrote it"))

    if e.reply_to and e.reply_to.rsplit("@", 1)[-1] != domain:
        out.append(_sig("reply_to_mismatch", "unusual", f"Replies would go to {e.reply_to}, not to the sender", "medium"))

    return out
