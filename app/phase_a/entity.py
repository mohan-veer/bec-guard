"""Entity checks: who is the sender, and do the headers back that up? Rules only."""
from app.phase_a.models import Email, OrgDirectory, Signal, VendorLedger

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

    if domain in FREE_EMAIL_DOMAINS:
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
