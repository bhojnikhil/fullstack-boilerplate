"""Enqueue, claim and finish jobs.

``enqueue`` only adds a row to the caller's session, so the job exists if and only if
the caller's transaction commits (a rolled-back request sends nothing). Workers claim
with ``FOR UPDATE SKIP LOCKED`` in a short transaction of their own and run the handler
outside any transaction. Delivery is at-least-once: a worker that dies mid-job leaves a
claim that expires, and the job runs again.
"""

import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory
from app.jobs.models import Job, JobStatus

BACKOFF_BASE = timedelta(seconds=15)
BACKOFF_CAP = timedelta(hours=1)
DEFAULT_MAX_ATTEMPTS = 6


def backoff(attempt: int, jitter: float | None = None) -> timedelta:
    """Delay before retrying after the ``attempt``-th failure: 15s, 30s, 60s ... capped, +-20%."""
    delay = min(BACKOFF_BASE * (2 ** min(max(attempt - 1, 0), 20)), BACKOFF_CAP)
    factor = 1 + (random.uniform(-0.2, 0.2) if jitter is None else jitter)
    result: timedelta = delay * factor
    return result


def enqueue(
    db: AsyncSession,
    kind: str,
    payload: Mapping[str, object] | None = None,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    delay: timedelta | None = None,
) -> Job:
    """Add a job to ``db``'s transaction. It becomes visible to workers on commit."""
    job = Job(
        kind=kind,
        payload=dict(payload or {}),
        max_attempts=max_attempts,
        status=JobStatus.QUEUED,
        attempts=0,
    )
    if delay is not None:
        job.run_at = func.now() + delay
    db.add(job)
    return job


async def enqueue_once(
    sessions: SessionFactory,
    kind: str,
    dedupe_key: str,
    *,
    max_attempts: int = 3,
) -> bool:
    """Enqueue unless a job with this key exists. Used for periodic schedules."""
    statement = (
        insert(Job)
        .values(
            kind=kind,
            payload={},
            status=JobStatus.QUEUED,
            attempts=0,
            max_attempts=max_attempts,
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing(
            index_elements=[Job.dedupe_key], index_where=Job.dedupe_key.is_not(None)
        )
        .returning(Job.id)
    )
    async with sessions.begin() as db:
        return (await db.execute(statement)).first() is not None


@dataclass(frozen=True)
class Claimed:
    id: UUID
    kind: str
    payload: dict[str, object]
    attempts: int
    max_attempts: int


async def claim(sessions: SessionFactory, lock_timeout: timedelta) -> Claimed | None:
    """Take the oldest due job, or one whose worker vanished. None if there is nothing."""
    due = or_(
        (Job.status == JobStatus.QUEUED) & (Job.run_at <= func.now()),
        (Job.status == JobStatus.RUNNING) & (Job.locked_at <= func.now() - lock_timeout),
    )
    async with sessions.begin() as db:
        job = (
            await db.execute(
                select(Job)
                .where(due)
                .order_by(Job.run_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.locked_at = func.now()
        job.attempts += 1
        claimed = Claimed(job.id, job.kind, dict(job.payload), job.attempts, job.max_attempts)
    return claimed


async def succeed(sessions: SessionFactory, job_id: UUID) -> None:
    async with sessions.begin() as db:
        await db.execute(delete(Job).where(Job.id == job_id))


async def fail(
    sessions: SessionFactory, job: Claimed, error: str, *, retry: bool = True
) -> JobStatus:
    """Schedule a retry with backoff, or kill the job when attempts are exhausted."""
    dead = not retry or job.attempts >= job.max_attempts
    values: dict[str, object] = {"last_error": error[:200], "locked_at": None}
    if dead:
        values |= {"status": JobStatus.DEAD, "payload": {}}
    else:
        values |= {
            "status": JobStatus.QUEUED,
            "run_at": func.now() + backoff(job.attempts),
        }
    async with sessions.begin() as db:
        await db.execute(update(Job).where(Job.id == job.id).values(**values))
    return JobStatus.DEAD if dead else JobStatus.QUEUED
