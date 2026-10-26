"""Org checks: is the sender domain a lookalike of a domain we know? (RDAP and Tavily checks come later.)"""
from functools import lru_cache

import dnstwist

from app.phase_a.models import OrgDirectory, Signal, VendorLedger

MAX_EDIT_DISTANCE = 2  # brief §6.2: edit distance 1–2


def known_domains(ledger: VendorLedger, org: OrgDirectory) -> list[str]:
    return [d for v in ledger.vendors for d in v.domains] + org.domains


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


def check_lookalike(domain: str, known_domains: list[str]) -> Signal:
    domain = _to_idna(domain.lower())
    for known in known_domains:
        if domain == known:
            continue
        if domain in _permutations(known) or edit_distance(domain, known) <= MAX_EDIT_DISTANCE:
            return Signal(code="lookalike_domain", group="org", verdict="unusual", weight="strong",
                          message=f"{domain} looks like {known} but is a different domain",
                          source="rules (dnstwist + edit distance)")
    return Signal(code="not_lookalike", group="org", verdict="fine",
                  message="Sender domain is not a lookalike of any known domain",
                  source="rules (dnstwist + edit distance)")
