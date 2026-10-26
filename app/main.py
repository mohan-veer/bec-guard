"""FastAPI app: API routes (pages come later)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import load_settings, log_modes
from app.phase_a.data import load_ledger, load_org
from app.phase_a.org import check_lookalike, known_domains

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_modes(load_settings())
    check_lookalike("warmup.invalid", known_domains(load_ledger(), load_org()))  # builds dnstwist cache (~1.4 s)
    yield


app = FastAPI(title="BEC Guard", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    s = load_settings()
    return {
        "status": "ok",
        "llm_mode": "mock" if s.llm_mock else "real",
        "tavily_mode": "mock" if s.tavily_mock else "real",
    }
