"""Per-tenant data profiles: the Gmail integration (tenant "riverbend") uses its own live data; the sample inbox
keeps the sample data. Both run in the same server."""
import asyncio

from app.phase_a import data
from app.phase_a.content import find_vendor
from app.phase_a.parse import parse_eml


def _email(sender, name="X", body="hi"):
    return parse_eml(f"Message-ID: <p@x>\nFrom: {name} <{sender}>\n\n{body}".encode())


def test_tenant_with_data_folder_gets_its_profile():
    assert data.profile_for_tenant("riverbend") == "riverbend"
    assert data.profile_for_tenant("someone-else") == "sample"
    assert data.profile_for_tenant("../etc") == "sample"


def test_default_profile_is_sample():
    assert data.load_org().domains == ["riverbenddental.com"]


def test_live_profile_has_real_test_accounts():
    with data.using_profile("riverbend"):
        people = {p.role: p.email for p in data.load_org().people}
        assert people["AP Clerk"] == "testorganization26@gmail.com"
        acme = next(v for v in data.load_ledger().vendors if v.id == "acme")
        assert acme.contacts[0].email == "test.vendor26@yahoo.com"
    assert data.load_org().domains == ["riverbenddental.com"]  # restored after the block


def test_free_provider_vendor_matched_by_exact_address_only():
    with data.using_profile("riverbend"):
        ledger = data.load_ledger()
        assert find_vendor(_email("test.vendor26@yahoo.com"), ledger).id == "acme"
        assert find_vendor(_email("someone.else@yahoo.com"), ledger) is None
        assert find_vendor(_email("someone.else@yahoo.com", name="Sam Ortiz"), ledger).id == "acme"  # name match


def test_profile_is_isolated_between_concurrent_tasks():
    async def read(profile):
        with data.using_profile(profile):
            await asyncio.sleep(0.01)
            return data.load_org().org_name, data.load_org().domains

    async def both():
        return await asyncio.gather(read("riverbend"), read("sample"))
    live, sample = asyncio.run(both())
    assert live[1] == ["riverbend.example"] and sample[1] == ["riverbenddental.com"]


def test_lookalike_address_is_linked_to_the_impersonated_vendor():
    # A1 as it really arrived: display name "Test Vendor" (not Sam's name), address imitating Sam's.
    with data.using_profile("riverbend"):
        ledger = data.load_ledger()
        assert find_vendor(_email("testvendor.26@outlook.com", name="Test Vendor"), ledger).id == "acme"
        assert find_vendor(_email("jane.doe@outlook.com", name="Jane"), ledger) is None


def test_a1_as_delivered_compares_bank_details_and_gives_callback(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    from app.phase_a.pipeline import analyze
    body = ("Our bank flagged the ACH for ACM-10437. Please send the $18,400.00 today by wire to our new account:\n"
            "Bank: Lakeshore Commerce Bank\nRouting: 999000666\nAccount: 000044019055\nThanks, Sam")
    with data.using_profile("riverbend"):
        r = asyncio.run(analyze(_email("testvendor.26@outlook.com", name="Test Vendor", body=body)))
    codes = {s.code for s in r.signals if s.verdict == "unusual"}
    assert {"address_lookalike", "bank_change", "method_change"} <= codes
    cb = next(s for s in r.signals if s.code == "callback_number")
    assert cb.data["phone"] == "(503) 555-0142"
