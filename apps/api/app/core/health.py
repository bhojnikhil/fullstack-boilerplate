from asyncio import timeout
from pathlib import Path
from threading import Lock

import structlog
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_session_factory
from app.core.errors import DomainError, ErrorCode, ErrorEnvelope

router = APIRouter(tags=["health"])
BYPASSES_RLS = text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
log = structlog.get_logger()
reported_unknown_sets: set[frozenset[str]] = set()
reported_unknown_sets_lock = Lock()


def warn_unknown_revisions(revisions: frozenset[str]) -> None:
    with reported_unknown_sets_lock:
        if revisions in reported_unknown_sets:
            return
        reported_unknown_sets.add(revisions)
    log.warning("database_revision_unknown", unknown_revision_ids=sorted(revisions))


def shipped_revisions() -> tuple[set[str], set[str]]:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    return set(scripts.get_heads()), {revision.revision for revision in scripts.walk_revisions()}


def applied_heads(connection: Connection) -> set[str]:
    return set(MigrationContext.configure(connection).get_current_heads())


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/ready", responses={503: {"model": ErrorEnvelope}})
async def readiness_check(request: Request) -> dict[str, str]:
    """Check DB connectivity and the migration revision."""
    try:
        async with timeout(3), get_session_factory(request)() as session:
            connection = await session.connection()
            heads = await connection.run_sync(applied_heads)
            bypasses_rls = await session.scalar(BYPASSES_RLS)
    except (SQLAlchemyError, TimeoutError) as err:
        raise DomainError(ErrorCode.NOT_READY) from err
    if bypasses_rls and not request.app.state.settings.local:
        # Row-level security does not apply to superusers and BYPASSRLS roles, so a
        # deployment connecting as one would silently lose its tenant isolation backstop.
        log.error("database_role_bypasses_row_level_security")
        raise DomainError(ErrorCode.NOT_READY)
    shipped_heads, known_revisions = request.app.state.shipped_revisions
    if not heads or heads & (known_revisions - shipped_heads):
        raise DomainError(ErrorCode.NOT_READY)
    unknown = heads - known_revisions
    if unknown:
        # Newer deploys can advance the schema while this image is still serving traffic.
        warn_unknown_revisions(frozenset(unknown))
    elif heads != shipped_heads:
        raise DomainError(ErrorCode.NOT_READY)
    return {"status": "ok"}
