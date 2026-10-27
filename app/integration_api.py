"""Integration API (/api/v1) for mail-client integrations: the Gmail Apps Script today, an Outlook client later.

Provider-neutral: emails arrive as raw RFC 822 (both Gmail and Microsoft Graph can export it). Every call needs an
X-BEC-Key header; the key identifies the tenant, and a tenant only ever sees its own results.
"""
import base64
import binascii
import hmac
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import jobs, ratelimit
from app.clients import mailbox as mailbox_client
from app.config import load_settings
from app.phase_a.data import SAMPLE, load_org, profile_for_tenant, using_profile
from app.phase_a.parse import parse_eml
from app.phase_b.mailbox_check import MailboxReport, check_mailbox, explain_findings

router = APIRouter(prefix="/api/v1")
DEMO_DIR = Path(__file__).parent.parent / "fixtures" / "demo"

Provider = Literal["gmail", "outlook"]
MessageId = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_\-=.:+]+$")  # Gmail hex ids, Graph ids


def tenant_for(x_bec_key: str | None) -> str:
    keys = load_settings().api_keys
    if not keys:
        raise HTTPException(status_code=503, detail="The integration API is not configured on this server")
    for secret, tenant in keys.items():
        if x_bec_key and hmac.compare_digest(x_bec_key.encode(), secret.encode()):
            return tenant
    raise HTTPException(status_code=401, detail="Missing or invalid API key")


class IngestRequest(BaseModel):
    provider: Provider
    mailbox: str = Field(min_length=3, max_length=320)
    message_id: str = MessageId
    raw: str = Field(description="The email as RFC 822, base64url-encoded")
    folder: Literal["inbox", "spam", "other"] = "inbox"


class StatusRequest(BaseModel):
    provider: Provider
    mailbox: str = Field(min_length=3, max_length=320)
    ids: list[str] = Field(max_length=100)


class SettingsRequest(BaseModel):
    provider: Provider
    mailbox: str = Field(min_length=3, max_length=320)
    # Gmail: the users.settings.* responses as returned by the Gmail API
    filters: dict = {}
    forwarding: dict = {}
    auto_forwarding: dict = {}
    # Outlook: the Graph messageRules response, plus folder id -> display name
    rules: dict = {}
    folders: dict[str, str] = {}


def _decode(raw: str) -> bytes:
    if len(raw) > jobs.MAX_RAW_B64:
        raise HTTPException(status_code=413, detail="Email is larger than 10 MB")
    try:
        return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="raw must be the email in base64url encoding")


def _summary(j: jobs.Job) -> dict:
    return {"message_id": j.message_id, "status": j.status, "label": j.label, "decision": j.decision,
            "headline": j.card["headline"] if j.card else None, "subject": j.subject, "sender": j.sender,
            "folder": j.folder, "created": j.created}


@router.post("/messages")
# async: submit() schedules the analysis on the running event loop
async def ingest(req: IngestRequest, x_bec_key: str | None = Header(default=None)):
    tenant = tenant_for(x_bec_key)
    try:
        email = parse_eml(_decode(req.raw))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read this as an email")
    if "@" not in email.from_addr:
        raise HTTPException(status_code=400, detail="This email has no sender (From) address")
    known = jobs.store.get(jobs.key(tenant, req.provider, req.mailbox, req.message_id))
    if not known or known.status == "error":  # only new analyses count against the limits
        ratelimit.ingest(tenant)
        ratelimit.spend_analysis()
    job, created = jobs.submit(tenant, req.provider, req.mailbox, req.message_id, req.folder, email)
    return JSONResponse(status_code=202 if created else 200, content=_summary(job))


@router.post("/messages/status")
def status(req: StatusRequest, x_bec_key: str | None = Header(default=None)):
    """Batch lookup so a scanner makes one call per run, not one per email."""
    tenant = tenant_for(x_bec_key)
    results = {}
    for mid in req.ids:
        j = jobs.store.get(jobs.key(tenant, req.provider, req.mailbox, mid))
        results[mid] = _summary(j) if j else {"message_id": mid, "status": "unknown"}
    return {"results": results}


@router.get("/messages/{provider}/{message_id}")
def get_message(provider: Provider, message_id: str, mailbox: str = Query(min_length=3, max_length=320),
                x_bec_key: str | None = Header(default=None)):
    tenant = tenant_for(x_bec_key)
    j = jobs.store.get(jobs.key(tenant, provider, mailbox, message_id))
    if not j:
        raise HTTPException(status_code=404, detail="Unknown message")
    return {**_summary(j), "card": j.card}


@router.get("/messages")
def recent(limit: int = Query(default=50, ge=1, le=200), x_bec_key: str | None = Header(default=None)):
    tenant = tenant_for(x_bec_key)
    mine = sorted((j for j in jobs.store.values() if j.tenant == tenant), key=lambda j: j.created, reverse=True)
    return {"items": [_summary(j) for j in mine[:limit]]}


@router.post("/mailbox-settings", response_model=MailboxReport)
async def mailbox_settings(req: SettingsRequest, x_bec_key: str | None = Header(default=None)):
    tenant = tenant_for(x_bec_key)
    if req.provider == "gmail":
        rules, fwd, auto = mailbox_client.normalize_gmail(req.filters, req.forwarding, req.auto_forwarding)
        snap = mailbox_client.MailboxSnapshot(provider="gmail", source="live", rules=rules, forwarding=fwd,
                                              auto_forward=auto)
    else:
        snap = mailbox_client.MailboxSnapshot(provider="outlook", source="live",
                                              rules=mailbox_client.normalize_graph(req.rules, req.folders))
    with using_profile(profile_for_tenant(tenant)):
        org_domains = load_org().domains + [req.mailbox.lower().rsplit("@", 1)[-1]]  # own mailbox domain is internal
    return await explain_findings(check_mailbox(snap, org_domains))


@router.get("/demo/history")
def demo_history(x_bec_key: str | None = Header(default=None)):
    """Backdated demo mailbox history for the caller's tenant (generated by scripts/make_demo_data.py)."""
    profile = profile_for_tenant(tenant_for(x_bec_key))
    path = DEMO_DIR / f"{profile}_history.json"
    if profile == SAMPLE or not path.is_file():
        raise HTTPException(status_code=404, detail="No demo history for this organization")
    return json.loads(path.read_text())
