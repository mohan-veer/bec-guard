import asyncio
from app.clients import rdap
from app.phase_a.org import check_domain_age

def _age(domain, monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    rdap._cache.clear()
    return asyncio.run(check_domain_age(domain))


def test_new_domain_is_medium(monkeypatch):
    s = _age("harbormedsupply.co", monkeypatch)
    assert (s.code, s.weight) == ("new_domain", "medium")
    assert "17 days ago" in s.message


def test_old_domain_is_fine(monkeypatch):
    s = _age("acmesupply.com", monkeypatch)
    assert s.code == "domain_age_ok" and s.verdict == "fine"


def test_unknown_domain_is_info(monkeypatch):
    s = _age("no-record.example", monkeypatch)
    assert s.code == "domain_age_unknown" and s.verdict == "info"
