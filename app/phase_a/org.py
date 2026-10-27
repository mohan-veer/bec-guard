"""Org checks: lookalike domain (rules), domain age (RDAP), web consensus + callback number (agent + Tavily)."""
import re
from datetime import date
from functools import lru_cache
from urllib.parse import urlparse

import dnstwist

from app.clients import rdap
from app.phase_a.models import OrgDirectory, Person, Signal, Vendor, VendorLedger
from app.phase_a.web_agent import find_official_contact, format_phone, on_domain, phone_digits, phones_in

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
                          message=f"Comes from {display or domain}, which imitates {known} but is a different address",
                          source="rules (dnstwist + edit distance)", data={"looks_like": known})
    return Signal(code="not_lookalike", group="org", verdict="fine",
                  message="The sender's web address doesn't imitate any company you work with",
                  source="rules (dnstwist + edit distance)")


# ---------- Domain age (RDAP) ----------

NEW_DOMAIN_DAYS = 90  # brief §6.2


async def check_domain_age(domain: str, today: date | None = None) -> Signal:
    registered = await rdap.registration_date(domain)
    src = "RDAP"
    if registered is None:
        return Signal(code="domain_age_unknown", group="org", verdict="info", source=src,
                      message=f"Couldn't find when {domain} was created")
    days = ((today or date.today()) - registered).days
    if days < NEW_DOMAIN_DAYS:
        return Signal(code="new_domain", group="org", verdict="unusual", weight="medium", source=src,
                      message=f"The web address {domain} was created only {days} days ago",
                      data={"registered": registered.isoformat()})
    return Signal(code="domain_age_ok", group="org", verdict="fine", source=src,
                  message=f"{domain} has existed since {registered.year}")


# ---------- Web consensus + callback number (Nemotron Super agent + Tavily) ----------

def _source(url: str | None, title: str | None, finding) -> list[dict]:
    """A link to a page that supported the conclusion, only for real web results and real web links."""
    if finding.simulated or not url or not re.match(r"^https?://[^\s/]+\.[^\s]+$", url):
        return []
    return [{"title": title or urlparse(url).netloc, "url": url}]


async def check_web_consensus(company: str, sender_domain: str, key: str, email_text: str,
                              vendor: Vendor | None, sender_on_file: bool = False) -> list[Signal]:
    """The company's official website and phone (Super agent + Tavily). sender_on_file: the address is a known
    contact, so a website-domain mismatch is expected (e.g. a small vendor on Gmail) and is info, not flagged.
    For a vendor on file the website's number is cross-checked against the records."""
    f = await find_official_contact(company, key, email_text)
    how = f"Nemotron Super + Tavily ({'agent' if f.method == 'agent' else 'fixed-step fallback'}, {f.searches} searches)"
    site = _source(f.official_url, f.official_title, f)
    phone_page = _source(f.phone_url, f.phone_title, f)
    with_site = {"sources": site} if site else {}
    with_phone = {"sources": phone_page} if phone_page else {}
    out: list[Signal] = []
    if not f.official_domain:
        out.append(Signal(code="web_consensus_unknown", group="org", verdict="info", source=how,
                          message=f"Couldn't find {company}'s official website online"))
    elif on_domain(sender_domain, f.official_domain):
        out.append(Signal(code="web_consensus_ok", group="org", verdict="fine", source=how, data=with_site,
                          message=f"Matches {company}'s official website, {f.official_domain}"))
    elif sender_on_file:
        out.append(Signal(code="web_consensus_other_domain", group="org", verdict="info", source=how, data=with_site,
                          message=f"{company}'s website is {f.official_domain}; this contact on file writes from {sender_domain}"))
    else:
        out.append(Signal(code="web_consensus_mismatch", group="org", verdict="unusual", weight="medium", source=how,
                          message=f"Says it's {company}, but {company}'s website is {f.official_domain} and this "
                                  f"came from {sender_domain}",
                          data={"company": company, "official_domain": f.official_domain, "sender_domain": sender_domain,
                                **with_site}))

    if f.phone:
        cb = callback_signal(company, f.phone, f.official_domain, how, f.phone_url, kind="web")
        cb.data.update(with_phone)
        out.append(cb)
        if vendor and vendor.official_phone:
            if phone_digits(f.phone) == phone_digits(vendor.official_phone):
                out.append(Signal(code="phones_agree", group="org", verdict="fine", source=how, data=with_phone,
                                  message=f"Your vendor records and {company}'s website list the same phone number "
                                          f"({f.phone})"))
            else:
                out.append(Signal(code="phones_differ", group="org", verdict="info", source=how, data=with_phone,
                                  message=f"{company}'s website lists {f.phone}; your vendor records have "
                                          f"{vendor.official_phone}"))
    return out


def check_email_phones(email_text: str, callbacks: list[Signal]) -> list[Signal]:
    """Scammers sign with their own number so the "verification" call reaches them. Compares numbers written in the
    email with the trusted ones (records, directory, official website). Never offers the email's number."""
    trusted = {phone_digits(c.data["phone"]): c.data for c in callbacks}
    if not trusted:
        return []
    out = []
    for digits in sorted(phones_in(email_text)):
        if digits in trusted:
            out.append(Signal(code="email_phone_matches", group="org", verdict="fine", source="rules",
                              message=f"The phone number in this email matches {_where(trusted[digits])}"))
        else:
            ref = next(iter(trusted.values()))
            out.append(Signal(code="email_phone_mismatch", group="org", verdict="unusual", weight="medium",
                              source="rules", data={"sources": ref["sources"]} if ref.get("sources") else {},
                              message=f"Gives {format_phone(digits)} to call, but {_where(ref)} lists {ref['phone']}"))
    return out


def _where(callback: dict) -> str:
    """Plain name of a trusted number's source: "your vendor records", "your staff directory", "Acme's website"."""
    kind = callback.get("kind")
    if kind == "records":
        return "your vendor records"
    if kind == "directory":
        return "your staff directory"
    return f"{callback['name']}'s website"


CALLBACK_PRIORITY = {"directory": 0, "records": 1, "web": 2}  # most trustworthy first


def callback_signal(name: str, phone: str, origin: str, source: str, url: str | None = None,
                    kind: str = "records") -> Signal:
    return Signal(code="callback_number", group="org", verdict="info", source=source,
                  message=f"Call {name} at {phone} (number from {origin}, not from this email)",
                  data={"name": name, "phone": phone, "from": origin, "url": url, "kind": kind})


def records_callback(vendor: Vendor) -> Signal:
    return callback_signal(vendor.name, vendor.official_phone, "your vendor records", "vendor ledger", kind="records")


def callback_from_directory(person: Person) -> Signal:
    return callback_signal(person.name, person.phone, "your org directory", "org directory", kind="directory")
