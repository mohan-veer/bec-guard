"""In-process analysis queue for emails sent by mail-client integrations.

The client (Gmail Apps Script, later an Outlook webhook) posts an email and gets an immediate answer; analysis runs
in the background with bounded concurrency; the client collects results later. Results are kept in memory, keyed by
(tenant, provider, mailbox, message id), so the same email is never analyzed twice. One process only: several
instances would need a shared store and a real queue (see PROJECT_NOTES).
"""
import asyncio
import contextvars
import logging
import time
from dataclasses import dataclass, field

from app.phase_a import data
from app.phase_a.card import build_card
from app.phase_a.models import Decision, Email
from app.phase_a.pipeline import analyze

MAX_RAW_B64 = 14 * 1024 * 1024  # ≈10 MB of email after base64 decoding
MAX_JOBS = 5000                 # oldest finished jobs are dropped beyond this (arbitrary)
MAX_CONCURRENT = 3              # analyses at once; each makes several LLM / Tavily calls (arbitrary)

LABELS = {Decision.VERIFY_BEFORE_PAYING: "verify", Decision.LOOKS_UNUSUAL: "unusual"}

log = logging.getLogger("bec_guard.jobs")


@dataclass
class Job:
    tenant: str
    provider: str
    mailbox: str
    message_id: str
    folder: str
    subject: str
    sender: str
    status: str = "queued"      # queued | processing | done | error
    label: str | None = None    # verify | unusual | none (once done)
    decision: str | None = None
    card: dict | None = None
    created: float = field(default_factory=time.time)
    email_time: float | None = None   # the email's own Date (epoch), if it has one


Key = tuple[str, str, str, str]
store: dict[Key, Job] = {}
_tasks: set[asyncio.Task] = set()
_sem: asyncio.Semaphore | None = None


def key(tenant: str, provider: str, mailbox: str, message_id: str) -> Key:
    return tenant, provider, mailbox.lower(), message_id


def reset_runtime() -> None:
    """Called at app startup: the semaphore must belong to the running event loop."""
    global _sem
    _sem = asyncio.Semaphore(MAX_CONCURRENT)


def _evict() -> None:
    if len(store) <= MAX_JOBS:
        return
    finished = sorted((j.created, k) for k, j in store.items() if j.status in ("done", "error"))
    for _, k in finished[: len(store) - MAX_JOBS]:
        del store[k]


async def _run(job: Job, email: Email) -> None:
    async with _sem:
        job.status = "processing"
        try:
            result = await analyze(email)
            job.decision = result.decision.value if result.decision else None
            job.label = LABELS.get(result.decision, "none")
            job.card = build_card(result, email).model_dump(mode="json")
            job.status = "done"
        except Exception:
            log.exception("analysis failed tenant=%s message_id=%s", job.tenant, job.message_id)
            job.status = "error"


def submit(tenant: str, provider: str, mailbox: str, message_id: str, folder: str, email: Email) -> tuple[Job, bool]:
    """Returns (job, created). An existing job is returned as is, unless it failed (then it is retried)."""
    k = key(tenant, provider, mailbox, message_id)
    existing = store.get(k)
    if existing and existing.status != "error":
        return existing, False
    job = Job(tenant=tenant, provider=provider, mailbox=mailbox.lower(), message_id=message_id, folder=folder,
              subject=email.subject, sender=email.from_addr_raw or email.from_addr,
              email_time=email.date.timestamp() if email.date else None)
    store[k] = job
    _evict()
    ctx = contextvars.copy_context()
    ctx.run(data.set_profile, data.profile_for_tenant(tenant))
    task = asyncio.create_task(_run(job, email), context=ctx)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job, True
