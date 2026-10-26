"""Org checks: lookalike domain (rules), domain age (RDAP), web consensus + callback number (agent + Tavily)."""
from datetime import date
from functools import lru_cache

import dnstwist

from app.clients import rdap
from app.phase_a.models import OrgDirectory, Person, Signal, Vendor, VendorLedger
from app.phase_a.web_agent import find_official_contact, on_domain

MAX_EDIT_DISTANCE = 2  # brief §6.2: edit distance 1–2


def known_domains(ledger: VendorLedger, org: OrgDirectory) -> list[str]:
    """Domains we own or our vendors own. Free providers are excluded: gmail.com isn't anyone's company domain, and
    ymail.com would otherwise look like a "lookalike" of gmail.com."""
    from app.phase_a.entity import FREE_EMAIL_DOMAINS
    return [d for d in [x for v in ledger.vendors for x in v.domains] + org.domains if d not in FREE_EMAIL_DOMAINS]


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@lru_cache
def _permutations(known: str) -> frozenset[str]:
    """dnstwist lookalikes of a known domain (homoglyphs incl. Unicode, omission, hyphenation, TLD swap, ...)."""
    f = dnstwist.Fuzzer(known)
    f.generate()
    return frozenset(d["domain"] for d in f.domains) - {known}


def _to_idna(domain: str) -> str:
    try:
        return domain.encode("idna").decode()
    except UnicodeError:
        return domain


def check_lookalike(domain: str, known_domains: list[str], display: str | None = None) -> Signal:
    """display: the sender domain as written (original case) for the message."""
    domain = _to_idna(domain.lower())
    for known in known_domains:
        if domain == known:
            continue
        if domain in _permutations(known) or edit_distance(domain, known) <= MAX_EDIT_DISTANCE:
            return Signal(code="lookalike_domain", group="org", verdict="unusual", weight="strong",
                          message=f"{display or domain} looks like {known} but is a different domain",
                          source="rules (dnstwist + edit distance)", data={"looks_like": known})
    return Signal(code="not_lookalike", group="org", verdict="fine",
                  message="Sender domain is not a lookalike of any known domain",
                  source="rules (dnstwist + edit distance)")


# ---------- Domain age (RDAP) ----------

NEW_DOMAIN_DAYS = 90  # brief §6.2


async def check_domain_age(domain: str, today: date | None = None) -> Signal:
    registered = await rdap.registration_date(domain)
    src = "RDAP"
    if registered is None:
        return Signal(code="domain_age_unknown", group="org", verdict="info", source=src,
                      message=f"Could not find when {domain} was registered")
    days = ((today or date.today()) - registered).days
    if days < NEW_DOMAIN_DAYS:
        return Signal(code="new_domain", group="org", verdict="unusual", weight="medium", source=src,
                      message=f"{domain} was registered {days} days ago", data={"registered": registered.isoformat()})
    return Signal(code="domain_age_ok", group="org", verdict="fine", source=src,
                  message=f"{domain} has been registered since {registered.year}")


# ---------- Web consensus + callback number (Nemotron Super agent + Tavily) ----------

async def check_web_consensus(company: str, sender_domain: str, key: str, email_text: str,
                              vendor: Vendor | None, sender_on_file: bool = False) -> list[Signal]:
    """sender_on_file: the address is a known contact, so a website-domain mismatch is expected (e.g. a small vendor
    on Gmail) and is shown as info, not flagged."""
    f = await find_official_contact(company, key, email_text)
    how = f"Nemotron Super + Tavily ({'agent' if f.method == 'agent' else 'fixed-step fallback'}, {f.searches} searches)"
    out: list[Signal] = []
    if not f.official_domain:
        out.append(Signal(code="web_consensus_unknown", group="org", verdict="info", source=how,
                          message=f"Could not confirm {company}'s official website"))
    elif on_domain(sender_domain, f.official_domain):
        out.append(Signal(code="web_consensus_ok", group="org", verdict="fine", source=how,
                          message=f"{f.official_domain} is {company}'s official website (found on {f.pages} pages)"))
    elif sender_on_file:
        out.append(Signal(code="web_consensus_other_domain", group="org", verdict="info", source=how,
                          message=f"{company}'s website is {f.official_domain}; this contact on file emails from {sender_domain}"))
    else:
        out.append(Signal(code="web_consensus_mismatch", group="org", verdict="unusual", weight="medium", source=how,
                          message=f"Web search shows {company}'s website is {f.official_domain}, "
                                  f"but this email came from {sender_domain}",
                          data={"official_domain": f.official_domain}))

    if f.phone:
        out.append(callback_signal(company, f.phone, f.official_domain, how, f.phone_url))
    elif vendor:
        out.append(callback_signal(vendor.name, vendor.official_phone, "your vendor records", "vendor ledger"))
    return out


def callback_signal(name: str, phone: str, origin: str, source: str, url: str | None = None) -> Signal:
    return Signal(code="callback_number", group="org", verdict="info", source=source,
                  message=f"Call {name} at {phone} (number from {origin}, not from this email)",
                  data={"name": name, "phone": phone, "from": origin, "url": url})


def callback_from_directory(person: Person) -> Signal:
    return callback_signal(person.name, person.phone, "your org directory", "org directory")
