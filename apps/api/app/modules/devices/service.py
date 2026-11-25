import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory
from app.integrations.push import (
    DEVICE_NOT_REGISTERED,
    PushBackend,
    PushMessage,
)
from app.jobs.queue import enqueue
from app.modules.devices.models import Device, PushTicket

PUSH_KIND = "send_push"
# Expo asks for receipts to be fetched at least 15 minutes after sending, and keeps them 24h.
RECEIPT_DELAY = timedelta(minutes=15)
RECEIPT_RETENTION = timedelta(hours=24)


async def register_device(
    db: AsyncSession, user_id: uuid.UUID, token: str, platform: str, app_version: str
) -> Device:
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


def enqueue_push(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    body: str,
    data: dict[str, object] | None = None,
) -> None:
    """Queue a notification for all of a user's devices (in the caller's transaction)."""
    enqueue(
        db,
        PUSH_KIND,
        {"user_id": str(user_id), "title": title, "body": body, "data": data or {}},
        max_attempts=5,
    )


async def send_push(
    sessions: SessionFactory,
    backend: PushBackend,
    user_id: uuid.UUID,
    title: str,
    body: str,
    data: dict[str, object],
) -> int:
    """Send to every device of the user. Returns how many messages were accepted.

    The provider call happens between two short transactions, so no connection or lock
    is held while waiting on the network.
    """
    async with sessions.begin() as db:
        devices = (
            await db.execute(
                select(Device.id, Device.expo_push_token)
                .where(Device.user_id == user_id)
                .order_by(Device.id)
            )
        ).all()
    if not devices:
        return 0
    tickets = await backend.send([PushMessage(token, title, body, data) for _, token in devices])
    accepted = 0
    gone: list[uuid.UUID] = []
    async with sessions.begin() as db:
        for (device_id, _), ticket in zip(devices, tickets, strict=True):
            if ticket.id is not None:
                accepted += 1
                db.add(PushTicket(ticket_id=ticket.id, device_id=device_id))
            elif ticket.error == DEVICE_NOT_REGISTERED:
                gone.append(device_id)
        await db.flush()
        if gone:
            await db.execute(delete(Device).where(Device.id.in_(sorted(gone))))
    return accepted


async def process_receipts(
    sessions: SessionFactory, backend: PushBackend, limit: int = 1000
) -> int:
    """Fetch receipts for tickets old enough; delete devices Expo says are gone.

    Returns the number of devices pruned. A ticket is removed once its receipt arrived,
    or after 24 hours (Expo's retention); until then a missing receipt is retried.
    Running twice concurrently is harmless: every statement is an idempotent delete.
    """
    now = datetime.now(UTC)
    async with sessions.begin() as db:
        rows = (
            await db.execute(
                select(PushTicket.ticket_id, PushTicket.device_id, PushTicket.created_at)
                .where(PushTicket.created_at <= now - RECEIPT_DELAY)
                .order_by(PushTicket.created_at, PushTicket.ticket_id)
                .limit(limit)
            )
        ).all()
    if not rows:
        return 0
    receipts = await backend.receipts([ticket_id for ticket_id, _, _ in rows])
    gone: set[uuid.UUID] = set()
    finished: list[str] = []
    for ticket_id, device_id, created_at in rows:
        receipt = receipts.get(ticket_id)
        if receipt is None:
            if created_at <= now - RECEIPT_RETENTION:
                finished.append(ticket_id)
            continue
        finished.append(ticket_id)
        if receipt.error == DEVICE_NOT_REGISTERED:
            gone.add(device_id)
    async with sessions.begin() as db:
        # Tickets before devices (tickets reference devices), each in key order.
        if finished:
            await db.execute(delete(PushTicket).where(PushTicket.ticket_id.in_(sorted(finished))))
        if gone:
            await db.execute(delete(Device).where(Device.id.in_(sorted(gone))))
    return len(gone)
