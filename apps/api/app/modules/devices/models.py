import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class Device(Base, UUIDMixin, TimestampMixin):
    """An installed app that can receive push notifications."""

    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_user_id", "user_id"),)
    __mapper_args__ = {"eager_defaults": True}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    # Unique across users: a device that signs in as someone else moves to that user.
    expo_push_token: Mapped[str] = mapped_column(String(255), unique=True)
    platform: Mapped[str] = mapped_column(String(16))
    app_version: Mapped[str] = mapped_column(String(32))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PushTicket(Base):
    """A message the push service accepted; its receipt is checked later."""

    __tablename__ = "push_tickets"
    __table_args__ = (Index("ix_push_tickets_created_at", "created_at"),)

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
