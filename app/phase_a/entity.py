"""Entity checks: who is the sender, and do the headers back that up? Rules only."""
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
            return f"Sender address is {p.name}'s address on file"
    for v in ledger.vendors:
        if any(c.email.lower() == addr for c in v.contacts):
            return f"Sender address matches past emails from {v.name}"
    return None


MIN_LOOKALIKE_USERNAME = 6  # shorter usernames ("ar", "info") collide too easily; arbitrary


def _address_lookalike(addr: str, ledger: VendorLedger, org: OrgDirectory) -> tuple[str, str] | None:
    """Free-provider impersonation: the same username on another provider, or a username 1–2 characters off
    (dots ignored), where either side is a free provider. Corporate domains are covered by the domain lookalike check.
    Returns (owner name, real address on file)."""
    local, domain = addr.rsplit("@", 1)
    on_file = [(p.name, p.email.lower()) for p in org.people] + \
              [(c.name if c.name else v.name, c.email.lower()) for v in ledger.vendors for c in v.contacts]
    for owner, real in on_file:
        real_local, real_domain = real.rsplit("@", 1)
        if real == addr or FREE_EMAIL_DOMAINS.isdisjoint({domain, real_domain}):
            continue
        a, b = local.replace(".", ""), real_local.replace(".", "")
        if len(b) >= MIN_LOOKALIKE_USERNAME and (a == b or edit_distance(a, b) <= 2):
            return owner, real
    return None


def check_entity(e: Email, ledger: VendorLedger, org: OrgDirectory) -> list[Signal]:
    out: list[Signal] = []
    addr, domain = e.from_addr, e.from_domain

    known = _known_sender_label(addr, ledger, org)
    if known:
        out.append(_sig("known_sender", "fine", known))
    else:
        out.append(_sig("first_contact", "unusual", "First contact with this sender: no history to compare.", "low"))
        on_file = _known_identities(ledger, org).get(e.from_name.strip().lower())
        if on_file:
            out.append(_sig("known_name_new_address", "unusual",
                            f'Uses the name "{e.from_name}" but from {addr}, not the address on file', "strong"))

    if not known:
        lookalike = _address_lookalike(addr, ledger, org)
        if lookalike:
            owner, real = lookalike
            out.append(Signal(code="address_lookalike", group="entity", verdict="unusual", weight="strong", source="rules",
                              message=f"Looks like {owner}'s address on file ({real}) but is a different address",
                              data={"looks_like": real, "owner": owner}))

    # A known contact who uses a free provider is normal (small vendors often do); only unknown senders are flagged.
    if domain in FREE_EMAIL_DOMAINS and not known:
        out.append(_sig("free_email", "unusual", f"Sent from a free email address ({domain}), not a company address", "medium"))

    if e.dmarc == "fail":
        out.append(_sig("dmarc_fail", "unusual", "Failed DMARC: the sender domain did not vouch for this email", "medium"))
    elif e.dmarc in (None, "none"):
        out.append(_sig("no_dmarc", "unusual", f"{domain} has no DMARC protection", "low"))
    elif e.spf == "pass" and e.dkim == "pass" and e.dmarc == "pass":
        out.append(_sig("email_auth_pass", "fine", f"Email really came from {domain} (SPF, DKIM, DMARC pass)"))

    if e.reply_to and e.reply_to.rsplit("@", 1)[-1] != domain:
        out.append(_sig("reply_to_mismatch", "unusual", f"Replies would go to {e.reply_to}, not to {domain}", "medium"))

    return out
