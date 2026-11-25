import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class JobStatus(StrEnum):
    QUEUED = "queued"
    # Claimed by a worker. A claim older than JOB_LOCK_TIMEOUT_SECONDS counts as lost.
    RUNNING = "running"
    # Attempts exhausted (or the job kind is unknown). Kept for inspection, payload cleared.
    DEAD = "dead"


class Job(Base):
    """One unit of background work. Succeeded jobs are deleted."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_run_at", "status", "run_at"),
        # Periodic schedules and callers that must not double-enqueue share a key.
        Index(
            "ux_jobs_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(64))
    # May hold personal data (a recipient address, a link). Deleted with the job on
    # success and cleared when the job dies.
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    status: Mapped[JobStatus] = mapped_column(String(16), default=JobStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str | None] = mapped_column(String(128))
    # The exception class only: messages can contain addresses or tokens.
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
