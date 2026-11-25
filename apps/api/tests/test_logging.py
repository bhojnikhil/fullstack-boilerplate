import json
import logging

import pytest

from app.core.logging import configure_logging


@pytest.mark.parametrize(
    "name", ["uvicorn.error", "sqlalchemy.engine", "alembic.runtime.migration"]
)
@pytest.mark.parametrize("env", ["production", "development"])
def test_stdlib_logs_render_and_redact_nested_exceptions(name, capsys, env):
    logger = logging.getLogger(name)
    configure_logging(env)
    logger.warning("stdlib log line")
    try:
        cause = ValueError("private cause")
        cause.add_note("private note")
        raise ExceptionGroup("private group", [cause])
    except ExceptionGroup:
        logger.exception("stdlib exception")

    output = capsys.readouterr().err
    assert "Logging error" not in output
    if env == "development":
        warning, error, traceback = output.split("\n", 2)
        assert "stdlib log line" in warning and name in warning
        assert "stdlib exception" in error and name in error
        stacks = json.loads(traceback)
    else:
        line, error = map(json.loads, output.splitlines())
        assert line["logger"] == error["logger"] == name
        assert line["event"] == "stdlib log line"
        assert line["level"] == "warning"
        assert error["event"] == "stdlib exception"
        stacks = error["exception"]
    assert stacks[0]["exceptions"][0][0]["exc_type"] == "ValueError"
    assert "private" not in output


def test_traceback_redaction_keeps_only_allowlisted_fields():
    from app.core.logging import redact_tracebacks

    stacks = [
        {
            "exc_type": "ValueError",
            "exc_value": "private message",
            "exc_notes": ["private note"],
            "syntax_error": "private source",
            "is_cause": False,
            "is_group": True,
            "future_field": "private value",
            "frames": [
                {"filename": "app.py", "lineno": 3, "name": "f", "locals": {"password": "private"}}
            ],
            "exceptions": [[{"exc_type": "KeyError", "exc_value": "private nested", "frames": []}]],
        }
    ]
    redacted = redact_tracebacks(stacks)
    assert "private" not in json.dumps(redacted)
    assert redacted[0]["frames"] == [{"filename": "app.py", "lineno": 3, "name": "f"}]
    assert redacted[0]["exceptions"][0][0]["exc_type"] == "KeyError"
