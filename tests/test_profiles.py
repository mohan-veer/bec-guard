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
