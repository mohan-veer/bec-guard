"""In-memory sliding-window rate limits. Every analysis spends Token Factory / Tavily credits, and the app is public.

- public checks (sample inbox, .eml upload, sample mailbox): per visitor IP, per minute and per day
- integration API: new emails per tenant per minute (duplicates are free)
- a global daily analysis budget: a hard ceiling on spend whatever happens
Limits are read from settings on every call. One process only (multi-instance would need a shared store).
"""
import math
import time
from collections import deque

from fastapi import HTTPException, Request

from app.config import load_settings

DAY = 86400


class SlidingWindow:
    def __init__(self):
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, window: float, now: float | None = None) -> float | None:
        """Records a hit and returns None, or returns the seconds to wait if the limit is reached (not recorded)."""
        now = time.time() if now is None else now
        q = self._hits.setdefault(key, deque())
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return q[0] + window - now
        q.append(now)
        return None

    def clear(self) -> None:
        self._hits.clear()


_public, _ingest, _budget = SlidingWindow(), SlidingWindow(), SlidingWindow()


def reset() -> None:
    for w in (_public, _ingest, _budget):
        w.clear()


def client_ip(request) -> str:
    """Behind the Cloudflare tunnel every request comes from 127.0.0.1; the visitor is in CF-Connecting-IP.
    On other hosts (e.g. Hugging Face) the first X-Forwarded-For entry. These headers are trusted because the app
    only listens behind a proxy (uvicorn binds 127.0.0.1 locally)."""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce(window: SlidingWindow, key: str, limit: int, seconds: int, message: str) -> None:
    retry = window.hit(key, limit, seconds)
    if retry is not None:
        raise HTTPException(status_code=429, detail=message, headers={"Retry-After": str(max(1, math.ceil(retry)))})


def public_check(request: Request) -> None:
    """FastAPI dependency for the public check endpoints."""
    s, ip = load_settings(), client_ip(request)
    _enforce(_public, f"{ip}:minute", s.rate_public_per_minute, 60, "Too many checks from your address. Try again in a minute.")
    _enforce(_public, f"{ip}:day", s.rate_public_per_day, DAY, "Daily limit of checks for your address reached.")


def ingest(tenant: str) -> None:
    _enforce(_ingest, tenant, load_settings().rate_ingest_per_minute, 60, "Too many new emails. Please retry shortly.")


def spend_analysis() -> None:
    _enforce(_budget, "global", load_settings().daily_analysis_budget, DAY,
             "BEC Guard's daily analysis limit has been reached. Please try again later.")
