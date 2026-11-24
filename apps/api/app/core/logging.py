import logging
from collections.abc import Sequence

import structlog
from structlog.typing import Processor

from app.core.config import Environment


def configure_logging(env: Environment) -> None:
    renderer: Processor = (
        structlog.dev.ConsoleRenderer()
        if env == "development"
        else structlog.processors.JSONRenderer()
    )
    processors: Sequence[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        renderer,
    ]
    structlog.configure(processors=processors)
    # Uvicorn access records include raw paths/query strings, including OAuth callback codes.
    logging.getLogger("uvicorn.access").disabled = True
