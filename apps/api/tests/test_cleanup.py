"""Periodic purge: expired rows go, live rows stay, locked rows are skipped."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text

from app.core.idempotency import IdempotencyRecord
from app.core.ratelimit import RateLimitWindow
from app.jobs import cleanup, queue
from app.jobs.handlers import PURGE_EXPIRED
from app.jobs.models import Job, JobStatus
from app.jobs.worker import drain
from app.modules.auth.models import (
    AccountToken,
    AccountTokenPurpose,
    AuthSession,
    RefreshToken,
    SessionRevocation,
    SignInMethod,
)

NOW = datetime.now(UTC)


def session_row(user_id, **overrides) -> AuthSession:
    values = {
        "user_id": user_id,
        "sign_in_method": SignInMethod.PASSWORD,
        "platform": "web",
        "authenticated_at": NOW,
        "last_used_at": NOW,
        "expires_at": NOW + timedelta(days=30),
    }
    return AuthSession(**{**values, **overrides})


async def count(session_factory, model) -> int:
    async with session_factory() as db:
        return await db.scalar(select(func.count()).select_from(model)) or 0


async def seed(session_factory, user) -> dict[str, list]:
    """For each table: [rows that must be purged], [rows that must stay]."""
    purge_sessions = [
        session_row(user.id, expires_at=NOW - timedelta(days=8)),
        session_row(
            user.id,
            revoked_at=NOW - timedelta(days=31),
            revoked_reason=SessionRevocation.LOGOUT,
        ),
    ]
    keep_sessions = [
        session_row(user.id),
        session_row(user.id, expires_at=NOW - timedelta(days=1)),
        session_row(user.id, revoked_at=NOW - timedelta(days=2), revoked_reason="logout"),
    ]
    async with session_factory.begin() as db:
        db.add_all(purge_sessions + keep_sessions)
        await db.flush()
        for row in purge_sessions + keep_sessions:
            db.add(RefreshToken(session_id=row.id, token_hash=f"hash-{row.id}"))

        def token(name, expires_at):
            return AccountToken(
                user_id=user.id,
                purpose=AccountTokenPurpose.VERIFY_EMAIL,
                token_hash=name,
                email=user.email,
                expires_at=expires_at,
            )

        db.add_all(
            [
                token("expired", NOW - timedelta(days=2)),
                token("recent", NOW - timedelta(hours=2)),
                token("valid", NOW + timedelta(hours=2)),
            ]
        )
        for key, expires in (("old", -1), ("live", 1)):
            db.add(
                IdempotencyRecord(
                    user_id=user.id,
                    key=key,
                    request_hash="h",
                    status=200,
                    body=None,
                    expires_at=NOW + timedelta(hours=expires),
                )
            )
        for key, resets in (("rule:old", -1), ("rule:live", 1)):
            db.add(RateLimitWindow(key=key, count=1, resets_at=NOW + timedelta(minutes=resets)))
        # (status, age in days): job payloads may hold one-time links, so every state expires.
        for status, age in (
            (JobStatus.DEAD, 4),
            (JobStatus.DONE, 4),
            (JobStatus.QUEUED, 4),
            (JobStatus.RUNNING, 4),
            (JobStatus.DEAD, 2),
            (JobStatus.QUEUED, 2),
        ):
            db.add(
                Job(
                    kind="x",
                    payload={},
                    status=status,
                    attempts=0,
                    max_attempts=1,
                    created_at=NOW - timedelta(days=age),
                    updated_at=NOW - timedelta(days=age),
                )
            )
    return {}


async def test_purge_removes_only_what_expired(session_factory, test_user):
    await seed(session_factory, test_user)
    counts = await cleanup.purge_expired(session_factory)
    assert counts == {
        "auth_sessions": 2,
        "account_tokens": 1,
        "idempotency_records": 1,
        "rate_limits": 1,
        "jobs": 4,
    }
    assert await count(session_factory, AuthSession) == 3
    async with session_factory() as db:
        assert set(await db.scalars(select(AccountToken.token_hash))) == {"recent", "valid"}
        assert set(await db.scalars(select(IdempotencyRecord.key))) == {"live"}
        assert set(await db.scalars(select(RateLimitWindow.key))) == {"rule:live"}
        statuses = sorted(await db.scalars(select(Job.status)))
        assert statuses == ["dead", "queued"]
    # Refresh tokens go with their sessions.
    assert await count(session_factory, RefreshToken) == 3
    assert await cleanup.purge_expired(session_factory) == dict.fromkeys(counts, 0)


async def test_purge_works_in_batches(session_factory, monkeypatch):
    monkeypatch.setattr(cleanup, "BATCH_SIZE", 3)
    async with session_factory.begin() as db:
        for number in range(10):
            db.add(
                RateLimitWindow(key=f"k:{number}", count=1, resets_at=NOW - timedelta(minutes=1))
            )
    assert await cleanup.purge_table(session_factory, cleanup.RULES[3]) == 10
    assert await count(session_factory, RateLimitWindow) == 0


async def test_purge_skips_rows_another_transaction_holds(session_factory):
    async with session_factory.begin() as db:
        for key in ("a", "b"):
            db.add(RateLimitWindow(key=key, count=1, resets_at=NOW - timedelta(minutes=1)))
    async with session_factory.begin() as holder:
        await holder.execute(text("select 1 from rate_limits where key = 'a' for update"))
        # Does not wait for the held row; purges the other one.
        assert await cleanup.purge_table(session_factory, cleanup.RULES[3]) == 1
    assert await cleanup.purge_table(session_factory, cleanup.RULES[3]) == 1


async def test_purge_runs_as_a_job(session_factory, job_context, test_user):
    await seed(session_factory, test_user)
    await queue.enqueue_once(session_factory, PURGE_EXPIRED, "test-purge")
    assert await drain(job_context) >= 1
    assert await count(session_factory, AuthSession) == 3


async def test_job_retention_is_configurable(session_factory):
    async with session_factory.begin() as db:
        db.add(
            Job(
                kind="x",
                payload={"link": "https://web.example.com/verify#token=t"},
                status=JobStatus.QUEUED,
                attempts=0,
                max_attempts=1,
                created_at=NOW - timedelta(days=2),
            )
        )
    assert (await cleanup.purge_expired(session_factory, job_retention_days=3))["jobs"] == 0
    assert (await cleanup.purge_expired(session_factory, job_retention_days=1))["jobs"] == 1
