"""``python -m app.jobs``: the worker entrypoint."""

import asyncio

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.observability import init_sentry
from app.factory import database_engine
from app.jobs.worker import build_context, install_signal_handlers, run_forever

log = structlog.get_logger()


async def main() -> None:
    config = Settings()
    configure_logging(config.env)
    init_sentry(config, "worker")
    engine = database_engine(config, pool_size=config.worker_concurrency + 1, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    ctx = build_context(config, sessions)
    stop = asyncio.Event()
    install_signal_handlers(stop)
    log.info("worker_started", concurrency=config.worker_concurrency)
    try:
        await run_forever(ctx, stop)
    finally:
        for backend in (ctx.email, ctx.push):
            close = getattr(backend, "aclose", None)
            if close is not None:
                await close()
        await engine.dispose()
        log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
