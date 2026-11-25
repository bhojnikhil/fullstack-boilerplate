"""The job queue: enqueue-on-commit, claiming, retries, periodic scheduling, workers."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.core.logging import configure_logging
from app.integrations.email import Email, EmailDeliveryError, enqueue_email
from app.integrations.email.templates import Template
from app.jobs import queue
from app.jobs.handlers import HANDLERS, JobContext
from app.jobs.models import Job
from app.jobs.worker import drain, period_key, run_forever, run_one, schedule_periodic

LOCK_TIMEOUT = timedelta(seconds=300)


async def jobs(session_factory) -> list[Job]:
    async with session_factory() as db:
        return list((await db.execute(select(Job).order_by(Job.created_at))).scalars())


async def add_job(session_factory, kind="test", payload=None, **kwargs) -> None:
    async with session_factory.begin() as db:
        queue.enqueue(db, kind, payload or {}, **kwargs)


def handlers_with(**custom):
    return {**HANDLERS, **custom}


async def test_enqueue_is_part_of_the_callers_transaction(session_factory):
    async with session_factory() as db:
        queue.enqueue(db, "test", {"n": 1})
        await db.flush()
        await db.rollback()
    assert await jobs(session_factory) == []

    await add_job(session_factory, payload={"n": 2})
    [job] = await jobs(session_factory)
    assert (job.kind, job.payload, job.status, job.attempts) == ("test", {"n": 2}, "queued", 0)


async def test_a_rolled_back_request_sends_no_email(session_factory, config, job_context):
    email = Email(Template.EMAIL_CHANGED, "p@example.com", "Subject", "text", "<p>html</p>")
    async with session_factory() as db:
        enqueue_email(db, email)
        await db.flush()
        await db.rollback()
    assert await drain(job_context) == 0
    assert job_context.email.outbox == []

    async with session_factory.begin() as db:
        enqueue_email(db, email)
    assert await drain(job_context) == 1
    assert job_context.email.outbox == [email]
    assert await jobs(session_factory) == []


async def test_successful_jobs_are_deleted(session_factory, job_context):
    seen = []

    async def handler(ctx, job_id, payload):
        seen.append(payload)

    await add_job(session_factory, payload={"a": 1})
    assert await run_one(job_context, handlers_with(test=handler))
    assert seen == [{"a": 1}]
    assert await jobs(session_factory) == []
    assert not await run_one(job_context, handlers_with(test=handler))


async def test_delayed_jobs_wait_for_their_time(session_factory, job_context):
    await add_job(session_factory, delay=timedelta(hours=1))
    assert await queue.claim(session_factory, LOCK_TIMEOUT) is None


async def test_failures_retry_with_backoff_then_die_without_payload(session_factory, job_context):
    async def broken(ctx, job_id, payload):
        raise RuntimeError("550 person@example.com is not a mailbox")

    await add_job(session_factory, payload={"to": "person@example.com"}, max_attempts=3)
    handlers = handlers_with(test=broken)
    for attempt in (1, 2):
        assert await run_one(job_context, handlers)
        [job] = await jobs(session_factory)
        assert (job.status, job.attempts, job.last_error) == ("queued", attempt, "RuntimeError")
        assert job.payload == {"to": "person@example.com"}
        # Not due again until the backoff has passed.
        assert not await run_one(job_context, handlers)
        async with session_factory.begin() as db:
            await db.execute(update(Job).values(run_at=func.now()))
    assert await run_one(job_context, handlers)
    [job] = await jobs(session_factory)
    assert (job.status, job.attempts, job.payload, job.last_error) == (
        "dead",
        3,
        {},
        "RuntimeError",
    )
    # Dead jobs are never claimed again.
    assert not await run_one(job_context, handlers)


async def test_failure_logs_carry_the_error_class_not_its_message(
    session_factory, job_context, capsys
):
    configure_logging("test")

    async def broken(ctx, job_id, payload):
        raise OSError("550 person@example.com is not a mailbox")

    await add_job(session_factory, max_attempts=1)
    await run_one(job_context, handlers_with(test=broken))
    output = capsys.readouterr().err
    assert "job_failed" in output
    assert "OSError" in output
    assert "person@example.com" not in output
    async with session_factory() as db:
        assert "person@example.com" not in (await db.scalar(select(Job.last_error)) or "")


def test_backoff_doubles_up_to_a_cap():
    delays = [queue.backoff(n, jitter=0).total_seconds() for n in (1, 2, 3, 4, 10, 50)]
    assert delays == [15, 30, 60, 120, 3600, 3600]
    low, high = queue.backoff(3, jitter=-0.2), queue.backoff(3, jitter=0.2)
    assert (low.total_seconds(), high.total_seconds()) == (48, 72)
    assert 48 <= queue.backoff(3).total_seconds() <= 72


async def test_unknown_kinds_die_immediately(session_factory, job_context):
    await add_job(session_factory, kind="from_a_newer_release", payload={"x": 1})
    assert await run_one(job_context)
    [job] = await jobs(session_factory)
    assert (job.status, job.last_error, job.payload) == ("dead", "UnknownJobKind", {})


async def test_handlers_are_cancelled_after_the_timeout(session_factory, config):
    fast = JobContext(
        config.model_copy(update={"job_timeout_seconds": 5, "job_lock_timeout_seconds": 30}),
        session_factory,
        email=None,  # type: ignore[arg-type]
        push=None,  # type: ignore[arg-type]
    )

    async def slow(ctx, job_id, payload):
        await asyncio.sleep(60)

    await add_job(session_factory)
    original = asyncio.timeout
    try:
        asyncio.timeout = lambda _seconds: original(0.05)  # type: ignore[assignment]
        await run_one(fast, handlers_with(test=slow))
    finally:
        asyncio.timeout = original  # type: ignore[assignment]
    [job] = await jobs(session_factory)
    assert (job.status, job.last_error) == ("queued", "TimeoutError")


async def test_a_vanished_workers_job_is_reclaimed_after_the_lock_timeout(
    session_factory, job_context
):
    await add_job(session_factory, payload={"a": 1})
    first = await queue.claim(session_factory, LOCK_TIMEOUT)
    assert first is not None and first.attempts == 1
    # Still locked: nobody else may take it.
    assert await queue.claim(session_factory, LOCK_TIMEOUT) is None
    async with session_factory.begin() as db:
        await db.execute(update(Job).values(locked_at=func.now() - timedelta(minutes=6)))
    again = await queue.claim(session_factory, LOCK_TIMEOUT)
    assert again is not None and (again.id, again.attempts) == (first.id, 2)


async def test_a_job_lost_on_its_last_attempt_is_not_run_again(session_factory, job_context):
    ran = []

    async def handler(ctx, job_id, payload):
        ran.append(job_id)

    await add_job(session_factory, max_attempts=1)
    assert await queue.claim(session_factory, LOCK_TIMEOUT) is not None
    async with session_factory.begin() as db:
        await db.execute(update(Job).values(locked_at=func.now() - timedelta(minutes=6)))
    await run_one(job_context, handlers_with(test=handler))
    assert ran == []
    [job] = await jobs(session_factory)
    assert (job.status, job.last_error) == ("dead", "WorkerLost")


async def test_concurrent_workers_never_claim_the_same_job(session_factory):
    for number in range(8):
        await add_job(session_factory, payload={"n": number})
    claims = await asyncio.gather(*(queue.claim(session_factory, LOCK_TIMEOUT) for _ in range(12)))
    taken = [claim.id for claim in claims if claim is not None]
    assert len(taken) == 8
    assert len(set(taken)) == 8


async def test_periodic_jobs_are_scheduled_once_per_interval(session_factory):
    periodic = {"tick": timedelta(minutes=10)}
    noon = datetime(2026, 11, 25, 12, 0, 1, tzinfo=UTC)
    assert await schedule_periodic(session_factory, periodic, noon) == 1
    # Another worker (or the next poll) in the same interval adds nothing.
    assert await schedule_periodic(session_factory, periodic, noon + timedelta(minutes=9)) == 0
    assert await schedule_periodic(session_factory, periodic, noon + timedelta(minutes=10)) == 1
    assert [job.kind for job in await jobs(session_factory)] == ["tick", "tick"]
    assert period_key("tick", timedelta(minutes=10), noon) != period_key(
        "tick", timedelta(minutes=10), noon + timedelta(minutes=10)
    )


async def test_worker_runs_periodic_and_queued_jobs_then_stops(session_factory, config):
    ran = []

    async def handler(ctx, job_id, payload):
        ran.append(payload)
        stop.set()

    stop = asyncio.Event()
    ctx = JobContext(
        config.model_copy(update={"job_poll_interval_seconds": 0.05, "worker_concurrency": 2}),
        session_factory,
        email=None,  # type: ignore[arg-type]
        push=None,  # type: ignore[arg-type]
    )
    await add_job(session_factory, payload={"hello": "worker"})
    HANDLERS["test"] = handler
    try:
        await asyncio.wait_for(run_forever(ctx, stop), 20)
    finally:
        del HANDLERS["test"]
    assert ran == [{"hello": "worker"}]
    assert {job.kind for job in await jobs(session_factory)} >= {"purge_expired"}


async def test_email_jobs_retry_until_the_provider_recovers(session_factory, job_context):
    attempts = []

    class Flaky:
        outbox: list = []

        async def send(self, email, *, key=None):
            attempts.append(key)
            if len(attempts) < 3:
                raise EmailDeliveryError("http_503")
            self.outbox.append(email)

    job_context.email = Flaky()  # type: ignore[assignment]
    async with session_factory.begin() as db:
        enqueue_email(db, Email(Template.EMAIL_CHANGED, "p@example.com", "S", "t", "<p>h</p>"))
    for _ in range(3):
        await run_one(job_context)
        async with session_factory.begin() as db:
            await db.execute(update(Job).values(run_at=func.now()))
    assert len(attempts) == 3
    # The same idempotency key on every attempt (the job id).
    assert len(set(attempts)) == 1 and attempts[0]
    assert len(Flaky.outbox) == 1
    assert await jobs(session_factory) == []


async def test_deferred_account_work_commits_its_emails_with_its_changes(
    client, outbox, session_factory
):
    response = await client.post(
        "/v1/auth/register",
        json={"email": "new@example.com", "name": "New", "password": "a-long-password-123"},
    )
    assert response.status_code in {200, 201, 202}
    assert [email.to for email in outbox] == ["new@example.com"]


async def test_a_stale_worker_cannot_finish_the_job_a_new_worker_reclaimed(
    session_factory, job_context
):
    await add_job(session_factory, payload={"n": 1})
    stale = await queue.claim(session_factory, LOCK_TIMEOUT)
    assert stale is not None
    async with session_factory.begin() as db:
        await db.execute(update(Job).values(locked_at=func.now() - timedelta(minutes=6)))
    current = await queue.claim(session_factory, LOCK_TIMEOUT)
    assert current is not None and current.id == stale.id
    assert current.lease_token != stale.lease_token

    # The paused worker wakes up: neither success nor failure touches the live claim.
    assert await queue.succeed(session_factory, stale) is False
    assert await queue.fail(session_factory, stale, "Boom") is None
    [job] = await jobs(session_factory)
    assert (job.status, job.attempts, job.lease_token, job.last_error) == (
        "running",
        2,
        current.lease_token,
        None,
    )

    assert await queue.succeed(session_factory, current) is True
    assert await jobs(session_factory) == []
    # A late result after the job is gone is also a no-op.
    assert await queue.succeed(session_factory, current) is False


async def test_a_periodic_job_runs_once_per_interval_even_after_it_succeeds(
    session_factory, job_context
):
    ran = []

    async def tick(ctx, job_id, payload):
        ran.append(job_id)

    periodic = {"tick": timedelta(minutes=10)}
    handlers = handlers_with(tick=tick)
    start = datetime(2026, 11, 25, 12, 0, 1, tzinfo=UTC)
    assert await schedule_periodic(session_factory, periodic, start) == 1
    assert await run_one(job_context, handlers)
    assert len(ran) == 1
    [marker] = await jobs(session_factory)
    assert (marker.status, marker.payload) == ("done", {})

    # The scheduler polls every 30 seconds: nothing may be enqueued again within the interval.
    for seconds in (30, 60, 300, 598):
        assert (
            await schedule_periodic(session_factory, periodic, start + timedelta(seconds=seconds))
            == 0
        )
    assert not await run_one(job_context, handlers)
    assert len(ran) == 1

    assert await schedule_periodic(session_factory, periodic, start + timedelta(minutes=10)) == 1
    assert await run_one(job_context, handlers)
    assert len(ran) == 2
