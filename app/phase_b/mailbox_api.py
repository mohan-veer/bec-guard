"""Mailbox check API (sample mailboxes). Live mailbox settings arrive through the integration API instead."""
from fastapi import APIRouter, HTTPException

from app.clients import mailbox
from app.phase_a.data import load_org
from app.phase_b.mailbox_check import MailboxReport, check_mailbox, explain_findings

router = APIRouter(prefix="/api/mailbox")
PROVIDERS = ("outlook", "gmail")


@router.post("/{provider}/check", response_model=MailboxReport)
async def check(provider: str):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown mailbox provider")
    return await explain_findings(check_mailbox(mailbox.read_fixture(provider), load_org().domains))
