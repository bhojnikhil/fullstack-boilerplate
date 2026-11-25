"""Job kinds and what runs for each. A handler raises to ask for a retry."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

import structlog

from app.core.config import Settings
from app.core.db import SessionFactory
from app.integrations.email import (
    SEND_EMAIL,
    EmailBackend,
    email_from_payload,
)
from app.integrations.push import PushBackend
from app.jobs.cleanup import PURGE_INTERVAL, purge_expired
from app.modules.devices.service import PUSH_KIND, process_receipts, send_push

log = structlog.get_logger()
PROCESS_RECEIPTS = "process_push_receipts"
PURGE_EXPIRED = "purge_expired"


@dataclass
class JobContext:
    config: Settings
    sessions: SessionFactory
    email: EmailBackend
    push: PushBackend
    extras: dict[str, object] = field(default_factory=dict)


Handler = Callable[[JobContext, uuid.UUID, dict[str, object]], Awaitable[None]]


async def handle_send_email(ctx: JobContext, job_id: uuid.UUID, payload: dict[str, object]) -> None:
    # The job id is the provider idempotency key: a retry after a lost response does not
    # send twice (providers that support keys).
    await ctx.email.send(email_from_payload(payload), key=str(job_id))
    log.info("email_sent", template=payload.get("template"))


async def handle_send_push(ctx: JobContext, job_id: uuid.UUID, payload: dict[str, object]) -> None:
    data = payload.get("data")
    accepted = await send_push(
        ctx.sessions,
        ctx.push,
        uuid.UUID(str(payload["user_id"])),
        str(payload["title"]),
        str(payload["body"]),
        data if isinstance(data, dict) else {},
    )
    log.info("push_sent", accepted=accepted)


async def handle_process_receipts(
    ctx: JobContext, job_id: uuid.UUID, payload: dict[str, object]
) -> None:
    pruned = await process_receipts(ctx.sessions, ctx.push)
    log.info("push_receipts_processed", pruned_devices=pruned)


async def handle_purge_expired(
    ctx: JobContext, job_id: uuid.UUID, payload: dict[str, object]
) -> None:
    await purge_expired(ctx.sessions)


HANDLERS: dict[str, Handler] = {
    SEND_EMAIL: handle_send_email,
    PUSH_KIND: handle_send_push,
    PROCESS_RECEIPTS: handle_process_receipts,
    PURGE_EXPIRED: handle_purge_expired,
}

# kind -> how often the worker's scheduler enqueues it (at most once per interval overall).
PERIODIC: dict[str, timedelta] = {
    PROCESS_RECEIPTS: timedelta(minutes=15),
    PURGE_EXPIRED: PURGE_INTERVAL,
}
