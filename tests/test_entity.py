import pytest

from app.phase_a.data import load_ledger, load_org
from app.phase_a.entity import check_entity
from app.phase_a.parse import parse_eml
from tests.helpers import codes, load_scenario


def _run(name):
    return check_entity(load_scenario(name), load_ledger(), load_org())


def test_known_vendor_sender_with_auth_pass():
    s = _run("06_legit_invoice_control.eml")
    assert codes(s) == set()
    assert {"known_sender", "email_auth_pass"} <= codes(s, "fine")


def test_fake_ceo_on_gmail():
    s = _run("03_fake_ceo_gift_cards.eml")
    assert {"known_name_new_address", "free_email", "first_contact"} <= codes(s)


def test_known_contact_name_on_lookalike_address():
    assert "known_name_new_address" in codes(_run("01_lookalike_vendor.eml"))


def test_new_vendor_is_first_contact_only():
    s = _run("05_fake_supplier_copied_name.eml")
    assert "first_contact" in codes(s)
    assert "known_name_new_address" not in codes(s)


def test_no_dmarc_is_low_weight():
    s = [x for x in _run("04_w2_lookalike_internal.eml") if x.code == "no_dmarc"]
    assert s and s[0].weight == "low"


def test_dmarc_fail_and_reply_to_mismatch_are_medium():
    raw = (b"Message-ID: <x@a.com>\nFrom: Mei Chen <orders@pacificpaperco.com>\n"
           b"Reply-To: mei@pacificpaper-billing.com\n"
           b"Authentication-Results: mx; spf=fail; dkim=fail; dmarc=fail\nSubject: s\n\nbody")
    s = check_entity(parse_eml(raw), load_ledger(), load_org())
    by_code = {x.code: x for x in s}
    assert by_code["dmarc_fail"].weight == "medium"
    assert by_code["reply_to_mismatch"].weight == "medium"


# ---------- free-email providers (live demo accounts are all on free providers) ----------

from app.phase_a.models import (AmountRange, BankAccount, Contact, OrgDirectory, Person, Vendor,  # noqa: E402
                                VendorLedger)


def _free_ledger():
    v = Vendor(id="acme", name="Acme Supply", domains=["yahoo.com"], official_website="", official_phone="(503) 555-0142",
               contacts=[Contact(name="Sam Ortiz", email="acmesupply.billing@yahoo.com", role="AR")],
               bank_account=BankAccount(bank_name="B", routing_number="999000111", account_last4="4821", account_holder="A"),
               payment_method="ACH", usual_amount=AmountRange(min=1, max=2), invoice_pattern=".*", remit_to="",
               past_invoices=[], past_emails=[])
    org = OrgDirectory(org_name="Riverbend", domains=["outlook.com"],
                       people=[Person(name="Dana Whitfield", role="CEO", email="dana.riverbend@outlook.com", phone="1")])
    return VendorLedger(vendors=[v]), org


def _free(sender: str, name: str = "Someone"):
    ledger, org = _free_ledger()
    e = parse_eml(f"Message-ID: <x@y>\nFrom: {name} <{sender}>\nAuthentication-Results: mx; spf=pass; dkim=pass; dmarc=pass\n\nhi".encode())
    return check_entity(e, ledger, org)


def test_known_contact_on_free_provider_is_not_flagged_as_free_email():
    s = _free("acmesupply.billing@yahoo.com", "Sam Ortiz")
    assert "free_email" not in codes(s) and "known_sender" in codes(s, "fine")


def test_same_username_on_another_provider_is_address_lookalike():
    s = {x.code: x for x in _free("acmesupply.billing@outlook.com")}
    assert s["address_lookalike"].weight == "strong"
    assert "acmesupply.billing@yahoo.com" in s["address_lookalike"].message
    assert s["address_lookalike"].data["looks_like"] == "acmesupply.billing@yahoo.com"


@pytest.mark.parametrize("sender", ["acmesupp1y.billing@yahoo.com", "acmesupply.bi11ing@gmail.com", "acme.supply.billing@yahoo.com"])
def test_username_one_or_two_chars_off_is_address_lookalike(sender):
    assert "address_lookalike" in codes(_free(sender))


@pytest.mark.parametrize("sender", ["jane.doe@yahoo.com", "billing@gmail.com", "sam.ortiz@acmesupply.com"])
def test_unrelated_addresses_are_not_address_lookalikes(sender):
    assert "address_lookalike" not in codes(_free(sender))


def test_vendor_username_on_an_unknown_domain_is_flagged():
    # Could be the vendor's new company address or a scammer's domain: nothing else catches it, and "call the number
    # on file" is the safe action either way.
    assert "address_lookalike" in codes(_free("acmesupply.billing@acmesupply.com"))


def test_unknown_free_sender_still_flagged_as_free_email():
    assert "free_email" in codes(_free("random.person@gmail.com"))
