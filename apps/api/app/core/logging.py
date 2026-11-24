import json
import logging
from collections.abc import Sequence
from typing import Any, TextIO

import structlog
from structlog.processors import ExceptionRenderer
from structlog.stdlib import ProcessorFormatter
from structlog.tracebacks import ExceptionDictTransformer
from structlog.typing import ExcInfo, Processor

from app.core.config import Environment

exception_dicts = ExceptionDictTransformer(show_locals=False)


def redact_tracebacks(stacks: list[dict[str, Any]]) -> None:
    for stack in stacks:
        # Messages, notes and syntax error snippets can contain request data or SQL.
        del stack["exc_value"], stack["exc_notes"], stack["syntax_error"]
        for nested in stack["exceptions"]:
            redact_tracebacks(nested)


def safe_tracebacks(exc_info: ExcInfo) -> list[dict[str, Any]]:
    stacks = exception_dicts(exc_info)
    redact_tracebacks(stacks)
    return stacks


def render_console_traceback(stream: TextIO, exc_info: ExcInfo) -> None:
    stream.write("\n" + json.dumps(safe_tracebacks(exc_info), indent=2))


def configure_logging(env: Environment) -> None:
    renderers: Sequence[Processor]
    if env == "development":
        renderers = [structlog.dev.ConsoleRenderer(exception_formatter=render_console_traceback)]
    else:
        renderers = [ExceptionRenderer(safe_tracebacks), structlog.processors.JSONRenderer()]
    shared_processors: Sequence[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[*shared_processors, ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    handler = logging.StreamHandler()
    handler.setFormatter(
        ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                ProcessorFormatter.remove_processors_meta,
                *renderers,
            ],
        )
    )
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)

    # Replace Uvicorn's built-in text handlers with the shared formatter.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    # Access and HTTP client records can include raw URLs, including OAuth codes.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
