"""Security audit trail.

Events are added to the request's unit of work, so they commit atomically with the
change they describe. Failures that must still be recorded raise a ``DomainError``
with ``commit=True``.

Never put secrets, tokens or raw personal data (emails, IP addresses) in ``details``;
use ``keyed_digest`` values where correlation is needed. ``user_id`` has no foreign
key: after an account is deleted its events remain as pseudonymous records.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.client import ClientInfo
from app.core.models import Base, UUIDMixin


class AuditEventType(StrEnum):
    ACCOUNT_REGISTERED = "account_registered"
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    REFRESH_TOKEN_REUSED = "refresh_token_reused"
    SESSION_REVOKED = "session_revoked"
    OTHER_SESSIONS_REVOKED = "other_sessions_revoked"
    REAUTHENTICATED = "reauthenticated"
    REAUTHENTICATION_FAILED = "reauthentication_failed"
    EMAIL_VERIFIED = "email_verified"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET = "password_reset"
    EMAIL_CHANGE_REQUESTED = "email_change_requested"
    EMAIL_CHANGED = "email_changed"
    GOOGLE_LINKED = "google_linked"
    GOOGLE_UNLINKED = "google_unlinked"
    ACCOUNT_DELETED = "account_deleted"


class AuditEvent(Base, UUIDMixin):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_user_id_created_at", "user_id", "created_at"),
        Index("ix_audit_events_created_at", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


def record_event(
    db: AsyncSession,
    event: AuditEventType,
    *,
    client: ClientInfo | None = None,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    **details: str | int | bool | None,
) -> None:
    db.add(
        AuditEvent(
            event=event,
            user_id=user_id,
            session_id=session_id,
            ip_hash=client.ip_hash if client else None,
            user_agent=client.user_agent if client else None,
            details=details,
        )
    )
