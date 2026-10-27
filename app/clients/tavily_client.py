"""Tavily web search. Errors return [].

Simulated (fixtures/tavily/search.json) when MOCK_MODE is on, there is no key, or the request belongs to the sample
inbox: its companies are fictional, so real web results would describe real, unrelated companies. Simulated results
come from the saved query closest to the one asked (the real model words its searches its own way).
"""
import asyncio
import json
import logging
import re
import weakref
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel
from tavily import AsyncTavilyClient

from app.config import load_settings
from app.phase_a import data

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "tavily" / "search.json"

log = logging.getLogger("bec_guard.tavily")
_cache: dict[tuple, list["SearchHit"]] = {}


class SearchHit(BaseModel):
    title: str = ""
    url: str
    content: str = ""
    score: float = 0.0


_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncTavilyClient]" = weakref.WeakKeyDictionary()
MIN_QUERY_OVERLAP = 0.6  # share of a saved query's words that must appear in the asked query (arbitrary)


def _client() -> AsyncTavilyClient:
    loop = asyncio.get_running_loop()  # one client per event loop (see llm._client)
    if loop not in _clients:
        _clients[loop] = AsyncTavilyClient(api_key=load_settings().tavily_api_key)
    return _clients[loop]


def simulated() -> bool:
    return load_settings().tavily_mock or data.current_profile() == data.SAMPLE


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _closest(fixtures: dict, query: str) -> list[dict]:
    asked, best, best_score = _words(query), [], 0.0
    for saved, entry in fixtures.items():
        if saved.startswith("_"):
            continue
        words = _words(saved)
        score = len(asked & words) / len(words) if words else 0
        if score > best_score:
            best, best_score = entry["results"], score
    return best if best_score >= MIN_QUERY_OVERLAP else []


def _mock(query: str, include_domains: list[str] | None) -> list[dict]:
    results = _closest(json.loads(FIXTURE.read_text()), query)
    if include_domains:  # behave like the real include_domains filter
        results = [r for r in results if any(_host(r["url"]) == d or _host(r["url"]).endswith("." + d)
                                             for d in include_domains)]
    return results


async def search(query: str, include_domains: list[str] | None = None, max_results: int = 5) -> list[SearchHit]:
    """Basic-depth search (1 credit). Results are cached per (query, domains) to save credits."""
    key = (query.strip().lower(), tuple(include_domains or ()), max_results)
    if key in _cache:
        return _cache[key]

    if simulated():
        results = _mock(query, include_domains)
    else:
        try:
            resp = await _client().search(query=query, search_depth="basic", max_results=max_results,
                                          include_domains=include_domains or None)
            results = resp.get("results", [])
            log.info("tavily query=%r domains=%s hits=%d", query, include_domains, len(results))
        except Exception as exc:
            log.error("tavily query=%r failed: %s", query, exc)
            return []  # not cached: may be transient

    _cache[key] = [SearchHit.model_validate(r) for r in results]
    return _cache[key]
