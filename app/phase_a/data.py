"""Loads seeded data per profile. "sample" = data/*.json (the sample inbox); a tenant with a folder under
data/tenants/<tenant>/ gets its own vendor ledger and org directory (the live Gmail integration).

The active profile is a context variable, so concurrent analyses for different tenants never mix data.
"""
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

from app.phase_a.models import OrgDirectory, VendorLedger

DATA_DIR = Path(__file__).parent.parent.parent / "data"
TENANTS_DIR = DATA_DIR / "tenants"
SAMPLE = "sample"

_profile: ContextVar[str] = ContextVar("data_profile", default=SAMPLE)


def _dir(profile: str) -> Path:
    return DATA_DIR if profile == SAMPLE else TENANTS_DIR / profile


def profile_for_tenant(tenant: str) -> str:
    safe = re.fullmatch(r"[a-z0-9_-]{1,64}", tenant or "")
    return tenant if safe and (TENANTS_DIR / tenant).is_dir() else SAMPLE


def current_profile() -> str:
    return _profile.get()


def set_profile(profile: str) -> None:
    """For a new task's context (see jobs.submit)."""
    _profile.set(profile)


@contextmanager
def using_profile(profile: str):
    token = _profile.set(profile)
    try:
        yield
    finally:
        _profile.reset(token)


@lru_cache
def _ledger(profile: str) -> VendorLedger:
    return VendorLedger.model_validate_json((_dir(profile) / "vendor_ledger.json").read_text())


@lru_cache
def _org(profile: str) -> OrgDirectory:
    return OrgDirectory.model_validate_json((_dir(profile) / "org_directory.json").read_text())


def load_ledger() -> VendorLedger:
    return _ledger(_profile.get())


def load_org() -> OrgDirectory:
    return _org(_profile.get())


@lru_cache
def _security(profile: str) -> dict:
    path = _dir(profile) / "security.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def load_security() -> dict:
    """Office hours and compliance contacts ({} = defaults, nobody to alert)."""
    return _security(_profile.get())
