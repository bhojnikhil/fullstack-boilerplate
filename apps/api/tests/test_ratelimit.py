"""Rate-limit backends (in-memory and Postgres) and the limiter's rules and lockouts."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.config import Settings
from app.core.errors import RateLimitedError
from app.core.ratelimit import (
    MemoryRateLimitBackend,
    PostgresRateLimitBackend,
    RateLimiter,
    RateLimitWindow,
    Rule,
    build_rate_limit_backend,
    lockout_for,
)

MINUTE = timedelta(minutes=1)


@pytest.fixture(params=["memory", "postgres"])
def backend(request, session_factory):
    if request.param == "memory":
        return MemoryRateLimitBackend()
    return PostgresRateLimitBackend(session_factory)


async def expire(backend, key: str) -> None:
    """Move a window's reset time into the past."""
    if isinstance(backend, MemoryRateLimitBackend):
        window = backend.windows[key]
        backend.windows[key] = type(window)(window.count, window.observed_at, window.observed_at)
        return
    async with backend.sessions.begin() as session:
        await session.execute(
            update(RateLimitWindow)
            .where(RateLimitWindow.key == key)
            .values(resets_at=datetime(2000, 1, 1, tzinfo=UTC))
        )


async def test_windows_count_and_reset(backend):
    first = await backend.hit("k", MINUTE)
    second = await backend.hit("k", MINUTE)
    assert (first.count, second.count) == (1, 2)
    assert second.resets_at == first.resets_at
    assert 55 <= second.retry_after <= 60
    assert (await backend.peek("k")).count == 2
    assert await backend.peek("other") is None

    await expire(backend, "k")
    assert await backend.peek("k") is None
    restarted = await backend.hit("k", MINUTE)
    assert restarted.count == 1

    await backend.reset("k")
    assert await backend.peek("k") is None


async def test_postgres_hits_are_atomic_under_concurrency(session_factory):
    backend = PostgresRateLimitBackend(session_factory)
    windows = await asyncio.gather(*(backend.hit("burst", MINUTE) for _ in range(20)))
    assert sorted(window.count for window in windows) == list(range(1, 21))
    async with session_factory() as session:
        [row] = await session.scalars(select(RateLimitWindow))
    # Identifiers are stored only as keyed hashes by the limiter; the raw key is opaque.
    assert (row.key, row.count) == ("burst", 20)


async def test_postgres_writes_survive_a_rolled_back_request(session_factory):
    backend = PostgresRateLimitBackend(session_factory)
    async with session_factory() as request_session:
        await request_session.execute(select(1))
        await backend.hit("failed-login", MINUTE)
        await request_session.rollback()
    assert (await backend.peek("failed-login")).count == 1


def test_memory_backend_prunes_expired_windows():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    backend = MemoryRateLimitBackend(clock=lambda: now)
    backend.MAX_KEYS = 3
    for key in "abc":
        asyncio.run(backend.hit(key, MINUTE))
    now += timedelta(minutes=2)
    asyncio.run(backend.hit("d", MINUTE))
    assert set(backend.windows) == {"d"}


def test_lockout_schedule():
    assert [lockout_for(n).total_seconds() for n in range(5, 12)] == [
        30,
        60,
        120,
        240,
        480,
        900,
        900,
    ]
    assert lockout_for(100) == timedelta(minutes=15)


async def test_limiter_rules_and_overrides(config: Settings):
    limiter = RateLimiter(MemoryRateLimitBackend(), config)
    rule = Rule("demo", 2, MINUTE)
    await limiter.hit(rule, "203.0.113.9")
    await limiter.hit(rule, "203.0.113.9")
    with pytest.raises(RateLimitedError) as raised:
        await limiter.hit(rule, "203.0.113.9")
    assert 55 <= raised.value.retry_after <= 60
    assert ("Retry-After", str(raised.value.retry_after)) in raised.value.headers
    await limiter.hit(rule, "203.0.113.10")  # Separate identifier, separate window.

    limiter.overrides["demo"] = Rule("demo", 5, MINUTE)
    await limiter.hit(rule, "203.0.113.9")


async def test_limiter_keys_do_not_contain_identifiers(config: Settings):
    backend = MemoryRateLimitBackend()
    limiter = RateLimiter(backend, config)
    await limiter.hit(Rule("login_account", 5, MINUTE), "person@example.com")
    [key] = backend.windows
    assert key.startswith("login_account:")
    assert "person" not in key and "example" not in key
    assert len(key) <= 100  # Fits rate_limits.key.


async def test_lockout_after_repeated_failures(config: Settings):
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    limiter = RateLimiter(MemoryRateLimitBackend(clock=lambda: now[0]), config)
    for _ in range(4):
        await limiter.record_failure("login", "id")
        await limiter.ensure_not_locked("login", "id")
    await limiter.record_failure("login", "id")
    with pytest.raises(RateLimitedError) as raised:
        await limiter.ensure_not_locked("login", "id")
    assert raised.value.retry_after == 30
    now[0] += timedelta(seconds=30)
    await limiter.ensure_not_locked("login", "id")

    await limiter.clear_failures("login", "id")
    await limiter.record_failure("login", "id")
    await limiter.ensure_not_locked("login", "id")


def test_backend_selection(config: Settings, session_factory):
    assert isinstance(build_rate_limit_backend(config, session_factory), MemoryRateLimitBackend)
    postgres = config.model_copy(update={"rate_limit_backend": "postgres"})
    assert isinstance(build_rate_limit_backend(postgres, session_factory), PostgresRateLimitBackend)


async def test_login_limits_work_with_the_postgres_backend(app, client, session_factory, test_user):
    app.state.rate_limiter.backend = PostgresRateLimitBackend(session_factory)
    body = {"email": "test@example.com", "password": "wrong-password"}
    for _ in range(5):
        assert (await client.post("/v1/auth/login", json=body)).status_code == 401
    locked = await client.post("/v1/auth/login", json={**body, "password": "testpassword123"})
    assert locked.status_code == 429
    assert 25 <= int(locked.headers["retry-after"]) <= 30


async def test_failed_sign_ins_do_not_exhaust_a_small_pool(
    test_db_engine, database_url, secret_key, test_user
):
    """Counters are written while the request holds a connection; sharing one pool
    would make each request wait on itself (M7)."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.factory import create_app

    async with test_db_engine.connect() as connection:
        schema = await connection.scalar(text("SELECT current_schema()"))
    url = database_url.update_query_dict({"options": f"-csearch_path={schema}"})
    config = Settings(
        env="test",
        database_url=url.render_as_string(hide_password=False),
        secret_key=secret_key,
        email_backend="memory",
        rate_limit_backend="postgres",
        _env_file=None,
    )
    engine = create_async_engine(url, pool_size=1, max_overflow=0, pool_timeout=2)
    app = create_app(config, async_sessionmaker(engine, expire_on_commit=False))
    body = {"email": "test@example.com", "password": "wrong-password"}
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client,
        ):
            responses = await asyncio.gather(
                *(client.post("/v1/auth/login", json=body) for _ in range(3))
            )
    finally:
        await engine.dispose()
    assert [response.status_code for response in responses] == [401, 401, 401]
