"""Fixed-window rate limiting with pluggable storage.

Counters are written outside the request's unit of work: a failed sign-in rolls
the request back, but its attempt must still count. The Postgres backend therefore
uses its own short transaction per operation, so no Redis is required.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import Request
from sqlalchemy import DateTime, Index, Integer, String, case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Settings
from app.core.db import SessionFactory
from app.core.errors import RateLimitedError
from app.core.models import Base
from app.core.security import keyed_digest

# Consecutive failed sign-ins (per account identifier) before the lockout starts.
FAILURE_THRESHOLD = 5
FAILURE_WINDOW = timedelta(hours=1)
FIRST_LOCKOUT = timedelta(seconds=30)
MAX_LOCKOUT = timedelta(minutes=15)


class RateLimitWindow(Base):
    __tablename__ = "rate_limits"
    __table_args__ = (Index("ix_rate_limits_resets_at", "resets_at"),)

    # "<rule>:<HMAC of the identifier>" so emails and IPs are not stored.
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    resets_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True)
class Window:
    count: int
    resets_at: datetime
    # The backend's clock when it read the window (the database clock for Postgres).
    observed_at: datetime

    @property
    def retry_after(self) -> int:
        return max(1, math.ceil((self.resets_at - self.observed_at).total_seconds()))


class RateLimitBackend(Protocol):
    async def hit(self, key: str, window: timedelta) -> Window:
        """Count one event; start a new window if the current one has ended."""

    async def peek(self, key: str) -> Window | None:
        """The current window, or None if there is none or it has ended."""

    async def reset(self, key: str) -> None: ...


class MemoryRateLimitBackend:
    """Per-process counters for tests and single-process development."""

    MAX_KEYS = 10_000

    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.clock = clock
        self.windows: dict[str, Window] = {}

    async def hit(self, key: str, window: timedelta) -> Window:
        now = self.clock()
        current = self.windows.get(key)
        if current is None or current.resets_at <= now:
            if len(self.windows) >= self.MAX_KEYS:
                self.windows = {k: w for k, w in self.windows.items() if w.resets_at > now}
            current = Window(1, now + window, now)
        else:
            current = Window(current.count + 1, current.resets_at, now)
        self.windows[key] = current
        return current

    async def peek(self, key: str) -> Window | None:
        now = self.clock()
        current = self.windows.get(key)
        if current is None or current.resets_at <= now:
            return None
        return Window(current.count, current.resets_at, now)

    async def reset(self, key: str) -> None:
        self.windows.pop(key, None)


class PostgresRateLimitBackend:
    """Atomic upserts on ``rate_limits`` using the database clock."""

    def __init__(self, sessions: SessionFactory) -> None:
        self.sessions = sessions

    async def hit(self, key: str, window: timedelta) -> Window:
        ended = RateLimitWindow.resets_at <= func.now()
        statement = (
            insert(RateLimitWindow)
            .values(key=key, count=1, resets_at=func.now() + window)
            .on_conflict_do_update(
                index_elements=[RateLimitWindow.key],
                set_={
                    "count": case((ended, 1), else_=RateLimitWindow.count + 1),
                    "resets_at": case(
                        (ended, func.now() + window), else_=RateLimitWindow.resets_at
                    ),
                },
            )
            .returning(RateLimitWindow.count, RateLimitWindow.resets_at, func.now())
        )
        async with self.sessions.begin() as session:
            count, resets_at, observed_at = (await session.execute(statement)).one()
        return Window(count, resets_at, observed_at)

    async def peek(self, key: str) -> Window | None:
        statement = select(RateLimitWindow.count, RateLimitWindow.resets_at, func.now()).where(
            RateLimitWindow.key == key, RateLimitWindow.resets_at > func.now()
        )
        async with self.sessions.begin() as session:
            row = (await session.execute(statement)).one_or_none()
        return Window(*row) if row is not None else None

    async def reset(self, key: str) -> None:
        async with self.sessions.begin() as session:
            await session.execute(delete(RateLimitWindow).where(RateLimitWindow.key == key))


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window: timedelta


def lockout_for(failures: int) -> timedelta:
    """30s at the threshold, doubling with each further failure, capped at 15 minutes."""
    doublings = min(failures - FAILURE_THRESHOLD, 10)
    return min(FIRST_LOCKOUT * (1 << doublings), MAX_LOCKOUT)


class RateLimiter:
    def __init__(
        self,
        backend: RateLimitBackend,
        config: Settings,
        overrides: Mapping[str, Rule] | None = None,
    ) -> None:
        self.backend = backend
        self.config = config
        # Tests (and operators embedding the app) can tighten or relax named rules.
        self.overrides = dict(overrides or {})

    def key(self, name: str, identifier: str) -> str:
        return f"{name}:{keyed_digest(self.config, 'rate-limit', identifier)[:48]}"

    async def hit(self, rule: Rule, identifier: str) -> None:
        rule = self.overrides.get(rule.name, rule)
        window = await self.backend.hit(self.key(rule.name, identifier), rule.window)
        if window.count > rule.limit:
            raise RateLimitedError(window.retry_after)

    async def ensure_not_locked(self, scope: str, identifier: str) -> None:
        """Reject while a progressive lockout from repeated failures is active."""
        lock = await self.backend.peek(self.key(f"{scope}_lock", identifier))
        if lock is not None:
            raise RateLimitedError(lock.retry_after)

    async def record_failure(self, scope: str, identifier: str) -> None:
        failures = await self.backend.hit(self.key(f"{scope}_failures", identifier), FAILURE_WINDOW)
        if failures.count >= FAILURE_THRESHOLD:
            await self.backend.hit(
                self.key(f"{scope}_lock", identifier), lockout_for(failures.count)
            )

    async def clear_failures(self, scope: str, identifier: str) -> None:
        await self.backend.reset(self.key(f"{scope}_failures", identifier))


def build_rate_limit_backend(config: Settings, sessions: SessionFactory) -> RateLimitBackend:
    if config.rate_limit_backend == "memory":
        return MemoryRateLimitBackend()
    return PostgresRateLimitBackend(sessions)


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter
