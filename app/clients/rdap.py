"""Domain registration date via RDAP (free, no key). Unknown/errors -> None.

Simulated (fixtures/rdap.json) in MOCK_MODE or for the sample inbox, whose domains belong to a fictional world.
"""
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from app.config import load_settings
from app.phase_a import data

RDAP_URL = "https://rdap.org/domain/{domain}"
FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "rdap.json"

log = logging.getLogger("bec_guard.rdap")
_cache: dict[str, date | None] = {}


def _http() -> httpx.AsyncClient:
    # rdap.org redirects to the registry's own RDAP server.
    return httpx.AsyncClient(follow_redirects=True, timeout=10)


def _registration(payload: dict) -> date | None:
    for event in payload.get("events", []):
        if event.get("eventAction") == "registration":
            return datetime.fromisoformat(event["eventDate"].replace("Z", "+00:00")).date()
    return None


def _mock(domain: str) -> date | None:
    value = json.loads(FIXTURE.read_text()).get(domain)
    if not value:
        return None
    if value.startswith("days_ago:"):
        return date.today() - timedelta(days=int(value.split(":")[1]))
    return date.fromisoformat(value)


async def registration_date(domain: str) -> date | None:
    domain = domain.strip().lower()
    if domain in _cache:
        return _cache[domain]

    if load_settings().mock_mode or data.current_profile() == data.SAMPLE:
        _cache[domain] = _mock(domain)
        return _cache[domain]

    try:
        async with _http() as client:
            resp = await client.get(RDAP_URL.format(domain=domain))
    except httpx.HTTPError as exc:
        log.error("rdap %s failed: %s", domain, exc)
        return None  # not cached: may be transient
    if resp.status_code == 404:
        _cache[domain] = None
    elif resp.is_success:
        _cache[domain] = _registration(resp.json())
    else:
        log.error("rdap %s returned HTTP %d", domain, resp.status_code)
        return None
    return _cache[domain]
