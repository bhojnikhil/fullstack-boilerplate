"""The worker process: claims jobs, runs handlers with a timeout, schedules periodic jobs."""

import asyncio
import contextlib
import signal
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from app.core.config import Settings
from app.core.db import SessionFactory
from app.integrations.email import build_email_backend
from app.integrations.push import build_push_backend
from app.jobs import queue
from app.jobs.handlers import HANDLERS, PERIODIC, Handler, JobContext
from app.jobs.models import JobStatus

log = structlog.get_logger()
HEARTBEAT_PATH = Path("/tmp/worker-heartbeat")  # noqa: S108 - per-container file


def period_key(kind: str, interval: timedelta, now: datetime) -> str:
    """One key per kind per interval: every worker computes the same, only one insert wins."""
    bucket = int(now.timestamp() // interval.total_seconds())
    return f"periodic:{kind}:{bucket}"


async def schedule_periodic(
    sessions: SessionFactory,
    periodic: Mapping[str, timedelta] = PERIODIC,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    created = 0
    for kind, interval in periodic.items():
        if await queue.enqueue_once(sessions, kind, period_key(kind, interval, now)):
            created += 1
    return created


async def run_one(ctx: JobContext, handlers: Mapping[str, Handler] = HANDLERS) -> bool:
    """Claim and run a single due job. False when the queue had nothing due."""
    lock_timeout = timedelta(seconds=ctx.config.job_lock_timeout_seconds)
    job = await queue.claim(ctx.sessions, lock_timeout)
    if job is None:
        return False
    handler = handlers.get(job.kind)
    if handler is None:
        log.error("job_kind_unknown", kind=job.kind)
        await queue.fail(ctx.sessions, job, "UnknownJobKind", retry=False)
        return True
    if job.attempts > job.max_attempts:
        # Claimed again after its worker vanished on the last attempt.
        await queue.fail(ctx.sessions, job, "WorkerLost", retry=False)
        return True
    try:
        async with asyncio.timeout(ctx.config.job_timeout_seconds):
            await handler(ctx, job.id, job.payload)
    except Exception as error:
        # The class name only: messages may contain addresses or tokens.
        name = type(error).__name__
        outcome = await queue.fail(ctx.sessions, job, name)
        log.warning(
            "job_failed", kind=job.kind, attempt=job.attempts, error=name, outcome=str(outcome)
        )
        if outcome == JobStatus.DEAD:
            log.error("job_dead", kind=job.kind, job_id=str(job.id))
    else:
        await queue.succeed(ctx.sessions, job.id)
    return True


async def drain(ctx: JobContext, handlers: Mapping[str, Handler] = HANDLERS) -> int:
    """Run due jobs until none are left (tests, and the worker's own catch-up)."""
    count = 0
    while await run_one(ctx, handlers):
        count += 1
    return count


async def run_forever(ctx: JobContext, stop: asyncio.Event) -> None:
    interval = ctx.config.job_poll_interval_seconds

    async def runner() -> None:
        while not stop.is_set():
            try:
                busy = await run_one(ctx)
            except Exception:
                # Database unavailable, etc.: back off instead of spinning.
                log.exception("worker_loop_error")
                busy = False
            if not busy:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), interval)

    async def scheduler() -> None:
        while not stop.is_set():
            # Liveness only (like /health): a database outage is logged and retried, and
            # restarting the worker would not fix it.
            HEARTBEAT_PATH.touch()
            try:
                await schedule_periodic(ctx.sessions)
            except Exception:
                log.exception("worker_scheduler_error")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), 30)

    tasks = [asyncio.create_task(scheduler())]
    tasks += [asyncio.create_task(runner()) for _ in range(ctx.config.worker_concurrency)]
    await asyncio.gather(*tasks)


def build_context(config: Settings, sessions: SessionFactory) -> JobContext:
    return JobContext(config, sessions, build_email_backend(config), build_push_backend(config))


def install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
