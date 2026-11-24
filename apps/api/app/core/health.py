from asyncio import timeout
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_session_factory
from app.core.errors import DomainError, ErrorCode, ErrorEnvelope

router = APIRouter(tags=["health"])


def migration_heads() -> set[str]:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    return set(ScriptDirectory.from_config(config).get_heads())


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
    except (SQLAlchemyError, TimeoutError) as err:
        raise DomainError(ErrorCode.NOT_READY) from err
    if heads != request.app.state.migration_heads:
        raise DomainError(ErrorCode.NOT_READY)
    return {"status": "ok"}
