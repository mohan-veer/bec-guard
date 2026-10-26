import pytest

from app.phase_a.org import check_lookalike, edit_distance

KNOWN = ["acmesupply.com", "checkingsolutions.com", "riverbenddental.com"]


@pytest.mark.parametrize("domain", [
    "acmesuppiy.com",          # I -> i homoglyph (scenario 1, after lowercasing)
    "acmesupp1y.com",          # 1 for l
    "checkingsolution.com",    # omission (brief example)
    "riverbend-dental.com",    # hyphenation (scenario 4)
    "acmesupply.co",           # TLD swap
    "acrnesupply.com",         # rn for m
    "acmesuplpy.com",          # transposition
])
def test_lookalikes_are_flagged(domain):
    s = check_lookalike(domain, KNOWN)
    assert s.code == "lookalike_domain" and s.weight == "strong"


@pytest.mark.parametrize("domain", ["acmesupply.com", "gmail.com", "harbormedsupply.co", "pacificpaperco.com"])
def test_exact_and_unrelated_domains_are_not_flagged(domain):
    assert check_lookalike(domain, KNOWN).code == "not_lookalike"


def test_message_names_the_real_domain():
    assert "acmesupply.com" in check_lookalike("acmesuppiy.com", KNOWN).message


def test_edit_distance():
    assert edit_distance("abc", "abc") == 0
    assert edit_distance("abc", "abd") == 1
    assert edit_distance("abc", "ab") == 1
    assert edit_distance("kitten", "sitting") == 3


def test_free_email_domains_are_never_lookalike_targets():
    from app.phase_a.org import known_domains
    from app.phase_a.models import OrgDirectory, VendorLedger
    doms = known_domains(VendorLedger(vendors=[]), OrgDirectory(org_name="o", domains=["gmail.com", "riverbend.com"], people=[]))
    assert doms == ["riverbend.com"]
    assert check_lookalike("ymail.com", doms).code == "not_lookalike"
