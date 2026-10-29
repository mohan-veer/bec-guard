"""FastAPI app: JSON API + the built React UI (frontend/dist)."""
import json
import logging
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import load_settings, log_modes
from app.phase_a.card import build_card
from app.phase_a.data import SAMPLE, load_ledger, load_org, using_profile
from app.phase_a.models import Email
from app.phase_a.org import check_lookalike, known_domains
from app.phase_a.parse import parse_eml
from app.phase_a.pipeline import analyze_events
from app import jobs, ratelimit
from app.integration_api import router as integration_router
from app.phase_b.mailbox_api import router as mailbox_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bec_guard.api")

ROOT = Path(__file__).parent.parent
SCENARIOS = ROOT / "scenarios"
FRONTEND_DIST = ROOT / "frontend" / "dist"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # arbitrary; generous for an email with a PDF


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_modes(load_settings())
    check_lookalike("warmup.invalid", known_domains(load_ledger(), load_org()))  # builds dnstwist cache (~1.4 s)
    jobs.reset_runtime()
    yield


app = FastAPI(title="BEC Guard", lifespan=lifespan)


# ---------- views ----------

class AttachmentView(BaseModel):
    filename: str
    content_type: str
    size: int


class EmailView(BaseModel):
    message_id: str
    from_name: str
    from_addr: str
    reply_to: str | None
    to: list[str]
    subject: str
    date: str | None
    body_text: str
    attachments: list[AttachmentView]


class ScenarioItem(BaseModel):
    id: str
    title: str
    from_name: str
    from_addr: str
    subject: str
    date: str | None
    has_attachments: bool


def email_view(e: Email) -> EmailView:
    return EmailView(
        message_id=e.message_id, from_name=e.from_name, from_addr=e.from_addr_raw or e.from_addr, reply_to=e.reply_to,
        to=e.to, subject=e.subject, date=e.date.isoformat() if e.date else None, body_text=e.body_text,
        attachments=[AttachmentView(filename=a.filename, content_type=a.content_type, size=len(a.data))
                     for a in e.attachments],
    )


@lru_cache
def _scenarios() -> dict[str, tuple[str, bytes]]:
    """id (file stem) -> (title, raw .eml). Only files listed in expected.json are served (no path input)."""
    spec = json.loads((SCENARIOS / "expected.json").read_text())["scenarios"]
    return {Path(s["file"]).stem: (s["title"], (SCENARIOS / s["file"]).read_bytes()) for s in spec}


def _scenario(scenario_id: str) -> tuple[str, bytes]:
    if scenario_id not in _scenarios():
        raise HTTPException(status_code=404, detail="Unknown scenario")
    return _scenarios()[scenario_id]


# ---------- streaming check ----------

def _check_stream(e: Email) -> StreamingResponse:
    """NDJSON events: email, gate, signals (per group), early (fail-fast warning), result (card) | error."""
    async def events():
        yield json.dumps({"type": "email", "email": email_view(e).model_dump()}) + "\n"
        try:
            async for ev in analyze_events(e):
                if ev["type"] == "result":
                    ev = {"type": "result", "card": build_card(ev["result"], e).model_dump(mode="json")}
                elif ev["type"] == "signals":
                    ev = {**ev, "signals": [s.model_dump(mode="json") for s in ev["signals"]]}
                yield json.dumps(ev) + "\n"
        except Exception:
            log.exception("check failed for message_id=%s", e.message_id)
            yield json.dumps({"type": "error", "message": "Something went wrong while checking this email."}) + "\n"
    return StreamingResponse(events(), media_type="application/x-ndjson")


# ---------- routes ----------

@app.get("/healthz")
def healthz():
    s = load_settings()
    return {
        "status": "ok",
        "llm_mode": "mock" if s.llm_mock else "real",
        "tavily_mode": "mock" if s.tavily_mock else "real",
    }


@app.get("/api/scenarios", response_model=list[ScenarioItem])
def list_scenarios():
    items = []
    for sid, (title, raw) in _scenarios().items():
        e = parse_eml(raw)
        items.append(ScenarioItem(id=sid, title=title, from_name=e.from_name, from_addr=e.from_addr_raw,
                                  subject=e.subject, date=e.date.isoformat() if e.date else None,
                                  has_attachments=bool(e.attachments)))
    return items


@app.get("/api/scenarios/{scenario_id}", response_model=EmailView)
def get_scenario(scenario_id: str):
    return email_view(parse_eml(_scenario(scenario_id)[1]))


@app.get("/api/scenarios/{scenario_id}/eml")
def download_scenario(scenario_id: str):
    return Response(_scenario(scenario_id)[1], media_type="message/rfc822",
                    headers={"content-disposition": f'attachment; filename="{scenario_id}.eml"'})


@app.get("/api/sample-records")
def sample_records():
    """The sample company's vendor records and staff directory (all fictional), so visitors can write test emails."""
    with using_profile(SAMPLE):
        return {"org": load_org().model_dump(), "vendors": [v.model_dump() for v in load_ledger().vendors]}


@app.post("/api/scenarios/{scenario_id}/check", dependencies=[Depends(ratelimit.public_check)])
def check_scenario(scenario_id: str):
    e = parse_eml(_scenario(scenario_id)[1])
    ratelimit.spend_analysis()
    return _check_stream(e)


@app.post("/api/check", dependencies=[Depends(ratelimit.public_check)])
async def check_upload(request: Request):
    """Body = the raw .eml bytes (no multipart, so no extra dependency)."""
    raw = await request.body()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Email is larger than 10 MB")
    try:
        e = parse_eml(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read this file as an email (.eml)")
    if "@" not in e.from_addr:
        raise HTTPException(status_code=400, detail="This file has no sender (From) address; is it an .eml file?")
    ratelimit.spend_analysis()
    return _check_stream(e)


app.include_router(mailbox_router)
app.include_router(integration_router)


if FRONTEND_DIST.is_dir():  # built UI; in dev, Vite serves it and proxies /api
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="ui")
