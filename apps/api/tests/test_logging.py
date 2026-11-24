import json
import logging

import pytest

from app.core.logging import configure_logging


@pytest.mark.parametrize(
    "name", ["uvicorn.error", "sqlalchemy.engine", "alembic.runtime.migration"]
)
def test_stdlib_logs_are_json_and_redact_nested_exceptions(name, capsys):
    logger = logging.getLogger(name)
    configure_logging("production")
    logger.warning("stdlib log line")
    try:
        cause = ValueError("private cause")
        cause.add_note("private note")
        raise ExceptionGroup("private group", [cause])
    except ExceptionGroup:
        logger.exception("stdlib exception")

    output = capsys.readouterr().err
    line, error = map(json.loads, output.splitlines())
    assert line["logger"] == error["logger"] == name
    assert line["event"] == "stdlib log line"
    assert line["level"] == "warning"
    assert error["event"] == "stdlib exception"
    assert error["exception"][0]["exceptions"][0][0]["exc_type"] == "ValueError"
    assert "private" not in output
