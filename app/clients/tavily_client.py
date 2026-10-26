"""Tavily web search. Mock mode: fixtures/tavily/search.json keyed by lowercased query. Errors return []."""
import json
import logging
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel
from tavily import AsyncTavilyClient

from app.config import load_settings

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "tavily" / "search.json"

log = logging.getLogger("bec_guard.tavily")
_cache: dict[tuple, list["SearchHit"]] = {}


class SearchHit(BaseModel):
    title: str = ""
    url: str
    content: str = ""
    score: float = 0.0


@lru_cache
def _client() -> AsyncTavilyClient:
    return AsyncTavilyClient(api_key=load_settings().tavily_api_key)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _mock(query: str, include_domains: list[str] | None) -> list[dict]:
    results = json.loads(FIXTURE.read_text()).get(query.strip().lower(), {"results": []})["results"]
    if include_domains:  # behave like the real include_domains filter
        results = [r for r in results if any(_host(r["url"]) == d or _host(r["url"]).endswith("." + d)
                                             for d in include_domains)]
    return results


async def search(query: str, include_domains: list[str] | None = None, max_results: int = 5) -> list[SearchHit]:
    """Basic-depth search (1 credit). Results are cached per (query, domains) to save credits."""
    key = (query.strip().lower(), tuple(include_domains or ()), max_results)
    if key in _cache:
        return _cache[key]

    if load_settings().tavily_mock:
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
