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
