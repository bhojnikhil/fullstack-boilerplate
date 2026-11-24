"""Atomic replay of committed authenticated mutations."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from starlette.responses import JSONResponse, Response

from app.core.errors import DomainError, ErrorCode
from app.core.models import Base

KEY_MAX_LENGTH = 128
REPLAY_TTL = timedelta(hours=24)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (Index("ix_idempotency_records_expires_at", "expires_at"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(KEY_MAX_LENGTH), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[int] = mapped_column(SmallInteger)
    body: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReplayResponseError(Exception):
    def __init__(self, record: IdempotencyRecord) -> None:
        # Copy before the unit of work unwinds and expires the ORM record.
        self.status = record.status
        self.body = record.body


async def replay_handler(request: Request, exc: ReplayResponseError) -> Response:
    if exc.status == 204:
        return Response(status_code=exc.status)
    return JSONResponse(exc.body, status_code=exc.status)


class Idempotency:
    def __init__(
        self, db: AsyncSession, record: IdempotencyRecord | None = None, digest: str = ""
    ) -> None:
        self._db = db
        self._record = record
        self._digest = digest

    def save[T: BaseModel | None](self, body: T, status: int = 200) -> T:
        if self._record is not None:
            self._record.request_hash = self._digest
            self._record.status = status
            self._record.body = body.model_dump(mode="json") if body is not None else None
            self._record.expires_at = datetime.now(UTC) + REPLAY_TTL
            self._db.add(self._record)
        return body


async def begin_idempotency(
    db: AsyncSession, user_id: UUID, key: str, request: Request
) -> Idempotency:
    if not 1 <= len(key) <= KEY_MAX_LENGTH or any(not 33 <= ord(char) <= 126 for char in key):
        raise DomainError(ErrorCode.INVALID_IDEMPOTENCY_KEY)

    target = (request.method.encode(), request.url.path.encode(), request.scope["query_string"])
    content_type = request.headers.get("content-type", "")
    media_type = content_type.partition(";")[0].strip().lower()
    body = await request.body()
    digest = request_digest((*target, media_type.encode(), body))

    # Transaction locks work through pgBouncer and release at commit or rollback.
    lock = sha256(b"idempotency:" + user_id.bytes + key.encode("ascii")).digest()[:8]
    lock_id = int.from_bytes(lock, "big", signed=True)
    if not await db.scalar(select(func.pg_try_advisory_xact_lock(lock_id))):
        raise DomainError(ErrorCode.IDEMPOTENCY_IN_PROGRESS)

    record = await db.get(IdempotencyRecord, (user_id, key))
    if record is not None and record.expires_at > datetime.now(UTC):
        if record.request_hash == digest:
            raise ReplayResponseError(record)
        # Pre-normalization records may still be within their replay window.
        if content_type != media_type and record.request_hash == request_digest(
            (*target, content_type.encode(), body)
        ):
            raise ReplayResponseError(record)
        raise DomainError(ErrorCode.IDEMPOTENCY_MISMATCH)

    # Defer adding a new record until after the endpoint succeeds. A read or flush
    # during the operation must not persist a record before status/body are known.
    if record is None:
        record = IdempotencyRecord(user_id=user_id, key=key)
    return Idempotency(db, record, digest)


def request_digest(parts: Iterable[bytes]) -> str:
    request_hash = sha256()
    # Frame each component so one component cannot be confused with part of another.
    for part in parts:
        request_hash.update(len(part).to_bytes(8, "big"))
        request_hash.update(part)
    return request_hash.hexdigest()
