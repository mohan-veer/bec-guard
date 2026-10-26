"""Fixture mailboxes load through the same normalizers as live payloads."""
import pytest

from app.clients import mailbox


@pytest.mark.parametrize("provider", ["outlook", "gmail"])
def test_fixture_snapshots_load(provider):
    snap = mailbox.read_fixture(provider)
    assert snap.provider == provider and snap.source == "fixture" and snap.rules
