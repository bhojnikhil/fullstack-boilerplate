import json
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEventType, record_event
from app.core.client import ClientInfo
from app.core.db import SessionFactory
from app.integrations.push import (
    PushBackend,
    PushMessage,
    classify_error,
)
from app.jobs.queue import backoff, enqueue
from app.modules.devices.models import Device, PushTicket

log = structlog.get_logger()
PUSH_KIND = "send_push"
# Expo asks for receipts to be fetched at least 15 minutes after sending, and keeps them 24h.
RECEIPT_DELAY = timedelta(minutes=15)
RECEIPT_RETENTION = timedelta(hours=24)
# A send that fails for some devices is retried for those devices only, this many times.
MAX_PUSH_ATTEMPTS = 5

# Job payloads sit in the database until delivered (docs/adr/0013), so push content is
# restricted to what a deep link needs: a few known keys with short scalar values.
ALLOWED_DATA_KEYS = frozenset({"type", "screen", "id", "url"})
MAX_TITLE = 100
MAX_BODY = 500
MAX_DATA_BYTES = 512


class PushPayloadError(ValueError):
    """The notification content is outside what the queue accepts."""


def validate_push_content(title: str, body: str, data: dict[str, object]) -> None:
    if not 0 < len(title) <= MAX_TITLE or not 0 < len(body) <= MAX_BODY:
        raise PushPayloadError("title or body length out of range")
    unknown = set(data) - ALLOWED_DATA_KEYS
    if unknown:
        raise PushPayloadError(f"data keys not allowed: {sorted(unknown)}")
    if any(not isinstance(v, str | int | bool) for v in data.values()):
        raise PushPayloadError("data values must be strings, integers or booleans")
    if len(json.dumps(data, separators=(",", ":"))) > MAX_DATA_BYTES:
        raise PushPayloadError("data is too large")


async def register_device(
    db: AsyncSession,
    user_id: uuid.UUID,
    token: str,
    platform: str,
    app_version: str,
    client: ClientInfo | None = None,
) -> Device:
    """Register or refresh a token for the signed-in user.

    A token that another user registered moves to the caller: the previous owner's row is
    deleted (never duplicated), so they stop receiving, and the move is audited. Two people
    sharing a phone (sign-out, sign-in) need this; the token identifies a device and is
    not a credential (docs/adr/0014).
    """
    previous_owner = await db.scalar(
        delete(Device)
        .where(Device.expo_push_token == token, Device.user_id != user_id)
        .returning(Device.user_id)
    )
    if previous_owner is not None:
        # The token itself is never written to the audit log.
        record_event(
            db,
            AuditEventType.DEVICE_TOKEN_REASSIGNED,
            client=client,
            user_id=user_id,
            previous_user_id=str(previous_owner),
            platform=platform,
        )
    statement = (
        insert(Device)
        .values(user_id=user_id, expo_push_token=token, platform=platform, app_version=app_version)
        .on_conflict_do_update(
            index_elements=[Device.expo_push_token],
            set_={
                "user_id": user_id,
                "platform": platform,
                "app_version": app_version,
                "last_seen_at": func.now(),
                "updated_at": func.now(),
            },
        )
        .returning(Device)
    )
    return (await db.execute(statement, execution_options={"populate_existing": True})).scalar_one()


async def unregister_device(db: AsyncSession, user_id: uuid.UUID, token: str) -> None:
    """Idempotent. Only the owner can remove a token."""
    await db.execute(
        delete(Device).where(Device.expo_push_token == token, Device.user_id == user_id)
    )


def push_payload(
    user_id: uuid.UUID,
    title: str,
    body: str,
    data: dict[str, object],
    device_ids: list[uuid.UUID] | None = None,
    attempt: int = 0,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "user_id": str(user_id),
        "title": title,
        "body": body,
        "data": data,
        "attempt": attempt,
    }
    if device_ids is not None:
        payload["device_ids"] = [str(device_id) for device_id in device_ids]
    return payload


def enqueue_push(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    body: str,
    data: dict[str, object] | None = None,
) -> None:
    """Queue a notification for all of a user's devices (in the caller's transaction).

    Raises ``PushPayloadError`` unless the content passes ``validate_push_content``.
    """
    validate_push_content(title, body, data or {})
    enqueue(db, PUSH_KIND, push_payload(user_id, title, body, data or {}), max_attempts=5)


def schedule_retry(
    db: AsyncSession, message: dict[str, object], device_ids: list[uuid.UUID], attempt: int
) -> bool:
    """Queue another send to just these devices, with backoff. False once attempts ran out."""
    if attempt + 1 >= MAX_PUSH_ATTEMPTS:
        log.error("push_retries_exhausted", devices=len(device_ids))
        return False
    payload = {**message, "device_ids": [str(i) for i in device_ids], "attempt": attempt + 1}
    enqueue(db, PUSH_KIND, payload, max_attempts=5, delay=backoff(attempt + 1))
    return True


async def send_push(
    sessions: SessionFactory,
    backend: PushBackend,
    user_id: uuid.UUID,
    title: str,
    body: str,
    data: dict[str, object],
    *,
    device_ids: list[uuid.UUID] | None = None,
    attempt: int = 0,
) -> int:
    """Send to the user's devices (or just ``device_ids``). Returns messages accepted.

    The provider call happens between two short transactions, so no connection or lock
    is held while waiting on the network. Per-device ticket errors are handled by class:
    dead tokens are deleted, transient errors are retried for those devices only, and
    permanent errors are logged (code and count only) and dropped.
    """
    query = select(Device.id, Device.expo_push_token).where(Device.user_id == user_id)
    if device_ids is not None:
        query = query.where(Device.id.in_(device_ids))
    async with sessions.begin() as db:
        devices = (await db.execute(query.order_by(Device.id))).all()
    if not devices:
        return 0
    tickets = await backend.send([PushMessage(token, title, body, data) for _, token in devices])
    message = push_payload(user_id, title, body, data)
    accepted = 0
    gone: list[uuid.UUID] = []
    retry: list[uuid.UUID] = []
    permanent: dict[str, int] = {}
    async with sessions.begin() as db:
        for (device_id, _), ticket in zip(devices, tickets, strict=True):
            if ticket.id is not None:
                accepted += 1
                db.add(PushTicket(ticket_id=ticket.id, device_id=device_id, message=message))
                continue
            outcome = classify_error(ticket.error or "unknown_error")
            if outcome == "gone":
                gone.append(device_id)
            elif outcome == "retry":
                retry.append(device_id)
            else:
                permanent[ticket.error or "unknown_error"] = (
                    permanent.get(ticket.error or "unknown_error", 0) + 1
                )
        await db.flush()
        if gone:
            await db.execute(delete(Device).where(Device.id.in_(sorted(gone))))
        if retry:
            schedule_retry(db, message, sorted(retry), attempt)
    for code, count in permanent.items():
        log.error("push_permanent_error", error=code, devices=count)
    return accepted


async def process_receipts(
    sessions: SessionFactory, backend: PushBackend, limit: int = 1000
) -> int:
    """Fetch receipts for tickets old enough; act on their errors by class.

    ``DeviceNotRegistered`` deletes the device (the return value counts those). Transient
    errors queue a retry for that device from the message stored with the ticket;
    permanent ones are logged by code. A ticket is removed once its receipt arrived, or
    after 24 hours (Expo's retention); until then a missing receipt is retried. Running
    twice concurrently is harmless: every statement is an idempotent delete, and a
    duplicate retry is the worst case.
    """
    now = datetime.now(UTC)
    async with sessions.begin() as db:
        rows = (
            await db.execute(
                select(
                    PushTicket.ticket_id,
                    PushTicket.device_id,
                    PushTicket.created_at,
                    PushTicket.message,
                )
                .where(PushTicket.created_at <= now - RECEIPT_DELAY)
                .order_by(PushTicket.created_at, PushTicket.ticket_id)
                .limit(limit)
            )
        ).all()
    if not rows:
        return 0
    receipts = await backend.receipts([row.ticket_id for row in rows])
    gone: set[uuid.UUID] = set()
    finished: list[str] = []
    retries: list[tuple[dict[str, object], uuid.UUID]] = []
    permanent: dict[str, int] = {}
    for ticket_id, device_id, created_at, message in rows:
        receipt = receipts.get(ticket_id)
        if receipt is None:
            if created_at <= now - RECEIPT_RETENTION:
                finished.append(ticket_id)
            continue
        finished.append(ticket_id)
        if receipt.ok:
            continue
        error = receipt.error or "unknown_error"
        outcome = classify_error(error)
        if outcome == "gone":
            gone.add(device_id)
        elif outcome == "retry":
            retries.append((message, device_id))
        else:
            permanent[error] = permanent.get(error, 0) + 1
    async with sessions.begin() as db:
        # Tickets before devices (tickets reference devices), each in key order.
        if finished:
            await db.execute(delete(PushTicket).where(PushTicket.ticket_id.in_(sorted(finished))))
        if gone:
            await db.execute(delete(Device).where(Device.id.in_(sorted(gone))))
        for message, device_id in retries:
            attempt = message.get("attempt")
            schedule_retry(db, message, [device_id], attempt if isinstance(attempt, int) else 0)
    for code, count in permanent.items():
        log.error("push_permanent_error", error=code, devices=count)
    return len(gone)
