"""Seeded mock data loads into the models and keeps the invariants the checks rely on."""
import json
import re
from pathlib import Path

from app.phase_a.models import OrgDirectory, VendorLedger

ROOT = Path(__file__).parent.parent


def _ledger() -> VendorLedger:
    return VendorLedger.model_validate_json((ROOT / "data/vendor_ledger.json").read_text())


def _org() -> OrgDirectory:
    return OrgDirectory.model_validate_json((ROOT / "data/org_directory.json").read_text())


def test_ledger_has_4_to_6_vendors_with_3_to_6_history_items():
    vendors = _ledger().vendors
    assert 4 <= len(vendors) <= 6
    for v in vendors:
        paid = [i for i in v.past_invoices if i.status == "paid"]
        assert 3 <= len(paid) <= 6, v.id
        assert 3 <= len(v.past_emails) <= 5, v.id


def test_past_invoices_match_pattern_and_account_on_file():
    for v in _ledger().vendors:
        for inv in v.past_invoices:
            assert re.match(v.invoice_pattern, inv.number), (v.id, inv.number)
            assert inv.bank_last4 == v.bank_account.account_last4, (v.id, inv.number)


def test_past_emails_come_from_known_domains():
    for v in _ledger().vendors:
        for e in v.past_emails:
            assert e.from_addr.split("@")[1] in v.domains, (v.id, e.from_addr)


def test_mock_data_is_fictional():
    # Fictional phone range and invalid (999-prefixed) routing numbers.
    for v in _ledger().vendors:
        assert "555-01" in v.official_phone
        assert v.bank_account.routing_number.startswith("999")
    for p in _org().people:
        assert "555-01" in p.phone


def test_org_directory_has_required_roles():
    roles = {p.role for p in _org().people}
    assert {"CEO", "CFO", "HR Lead", "AP Clerk"} <= roles


def test_every_scenario_file_exists():
    spec = json.loads((ROOT / "scenarios/expected.json").read_text())["scenarios"]
    assert len(spec) == 7
    for s in spec:
        assert (ROOT / "scenarios" / s["file"]).is_file(), s["file"]
