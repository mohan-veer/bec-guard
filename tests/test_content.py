from decimal import Decimal

from app.phase_a.content import check_request_keywords, compare_to_ledger, extract_payment_details, find_vendor
from app.phase_a.data import load_ledger
from tests.helpers import codes, load_scenario


def _vendor(vid):
    return next(v for v in load_ledger().vendors if v.id == vid)


def test_extract_from_bank_change_body():
    d = extract_payment_details(load_scenario("02_hacked_vendor_thread.eml").body_text)
    assert d.bank_name == "Pacific Crest Bank"
    assert d.routing_number == "999000222"
    assert d.account_last4 == "7731"
    assert d.account_holder == "Acme Supply LLC"
    assert d.method == "wire"
    assert d.amount == Decimal("18400.00")
    assert d.invoice_number == "ACM-10437"


def test_extract_ending_digits_and_ach():
    d = extract_payment_details(load_scenario("06_legit_invoice_control.eml").body_text)
    assert d.account_last4 == "5567"
    assert d.method == "ACH"
    assert d.amount == Decimal("1240.00")
    assert d.invoice_number == "PPC-2026-0412"
    assert d.po == "PO-2026-0119"


def test_bank_change_message_has_old_and_new_accounts():
    d = extract_payment_details(load_scenario("02_hacked_vendor_thread.eml").body_text)
    s = compare_to_ledger(d, _vendor("acme"))
    bank = next(x for x in s if x.code == "bank_change")
    assert bank.weight == "strong"
    assert "7731" in bank.message and "4821" in bank.message and "6 invoices" in bank.message
    assert "method_change" in codes(s)
    assert "amount_in_range" in codes(s, "fine")


def test_legit_invoice_has_no_unusual_findings():
    d = extract_payment_details(load_scenario("06_legit_invoice_control.eml").body_text)
    s = compare_to_ledger(d, _vendor("pacificpaper"))
    assert codes(s) == set()
    assert {"bank_account_matches", "amount_in_range", "invoice_format_ok"} <= codes(s, "fine")


def test_amount_out_of_range_and_bad_invoice_format():
    d = extract_payment_details("Invoice PPC-99 for $9,999.00, ACH to account ending 5567")
    s = compare_to_ledger(d, _vendor("pacificpaper"))
    assert {"amount_out_of_range", "invoice_format"} <= codes(s)
    assert next(x for x in s if x.code == "amount_out_of_range").weight == "medium"


def test_no_bank_details_means_no_bank_signal():
    d = extract_payment_details(load_scenario("01_lookalike_vendor.eml").body_text)
    s = compare_to_ledger(d, _vendor("acme"))
    assert "bank_change" not in codes(s)


def test_find_vendor_by_domain_then_by_contact_name():
    ledger = load_ledger()
    assert find_vendor(load_scenario("06_legit_invoice_control.eml"), ledger).id == "pacificpaper"
    assert find_vendor(load_scenario("01_lookalike_vendor.eml"), ledger).id == "acme"   # "Sam Ortiz" on lookalike
    assert find_vendor(load_scenario("05_fake_supplier_copied_name.eml"), ledger) is None


def test_request_keywords():
    assert "gift_card_request" in codes(check_request_keywords(load_scenario("03_fake_ceo_gift_cards.eml").body_text))
    assert "sensitive_data_request" in codes(check_request_keywords(load_scenario("04_w2_lookalike_internal.eml").body_text))
    assert codes(check_request_keywords(load_scenario("06_legit_invoice_control.eml").body_text)) == set()


def test_invoice_on_file_uses_its_po_and_is_recognised_as_open():
    d = extract_payment_details(load_scenario("02_hacked_vendor_thread.eml").body_text)
    s = compare_to_ledger(d, _vendor("acme"))
    assert "po_missing" not in codes(s)
    assert "invoice_open_on_file" in codes(s, "fine")


def test_invoice_already_paid_is_flagged():
    d = extract_payment_details("Please pay invoice ACM-10436 ($19,800.00)")
    s = compare_to_ledger(d, _vendor("acme"))
    paid = next(x for x in s if x.code == "invoice_already_paid")
    assert paid.weight == "medium"
