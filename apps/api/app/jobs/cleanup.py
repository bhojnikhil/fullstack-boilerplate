"""Periodic deletion of rows that can no longer matter.

Each rule deletes in batches, skipping rows another transaction holds, so a purge never
waits on (or blocks) request traffic. Only counts are logged.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult, text

from app.core.db import SessionFactory

log = structlog.get_logger()
BATCH_SIZE = 5000


@dataclass(frozen=True)
class PurgeRule:
    table: str
    # Fixed SQL fragments (never user input): rows matching are deleted.
    condition: str


# Retention: an expired session stays a week after expiry and a revoked one a month
# after revocation (support and reuse-detection forensics); refresh tokens go with their
# session (ON DELETE CASCADE). Tokens and idempotency records are useless once expired.
RULES = (
    PurgeRule(
        "auth_sessions",
        "expires_at < now() - interval '7 days' or revoked_at < now() - interval '30 days'",
    ),
    PurgeRule("account_tokens", "expires_at < now() - interval '1 day'"),
    PurgeRule("idempotency_records", "expires_at < now()"),
    PurgeRule("rate_limits", "resets_at < now()"),
    PurgeRule("jobs", "status = 'dead' and updated_at < now() - interval '14 days'"),
)


async def purge_table(sessions: SessionFactory, rule: PurgeRule) -> int:
    statement = text(
        f"delete from {rule.table} where ctid in ("  # noqa: S608 - fixed identifiers
        f"select ctid from {rule.table} where {rule.condition} limit :batch "
        "for update skip locked)"
    )
    total = 0
    while True:
        async with sessions.begin() as db:
            result = cast(CursorResult[Any], await db.execute(statement, {"batch": BATCH_SIZE}))
            deleted = int(result.rowcount)
        total += deleted
        if deleted < BATCH_SIZE:
            return total


async def purge_expired(sessions: SessionFactory) -> dict[str, int]:
    counts = {}
    for rule in RULES:
        counts[rule.table] = await purge_table(sessions, rule)
    log.info("purged_expired_rows", **counts)
    return counts


PURGE_INTERVAL = timedelta(hours=1)
