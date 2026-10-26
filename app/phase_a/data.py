"""Loads the seeded mock data once."""
from functools import lru_cache
from pathlib import Path

from app.phase_a.models import OrgDirectory, VendorLedger

DATA_DIR = Path(__file__).parent.parent.parent / "data"


@lru_cache
def load_ledger() -> VendorLedger:
    return VendorLedger.model_validate_json((DATA_DIR / "vendor_ledger.json").read_text())


@lru_cache
def load_org() -> OrgDirectory:
    return OrgDirectory.model_validate_json((DATA_DIR / "org_directory.json").read_text())
