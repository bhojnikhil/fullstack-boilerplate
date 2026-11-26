"""Sentry, enabled only when SENTRY_DSN is set. Nothing is imported or sent otherwise."""

import re
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from app.core.config import Settings, secret_value

JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
BEARER = re.compile(r"(?i)\b(bearer|basic|token)\s+\S+")
EMAIL = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+")
URL_QUERY = re.compile(r"(https?://[^\s?#'\"]+)[?#][^\s'\"]*")
HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")
LONG_TOKEN = re.compile(r"[A-Za-z0-9_+/=-]{40,}")
REDACTED = "[redacted]"


def redact(text: str) -> str:
    """Remove what commonly leaks through messages: addresses, tokens, secrets in URLs."""
    text = JWT.sub(REDACTED, text)
    text = BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = EMAIL.sub(REDACTED, text)
    text = URL_QUERY.sub(lambda m: f"{m.group(1)}?{REDACTED}", text)
    text = HEX.sub(REDACTED, text)
    return LONG_TOKEN.sub(REDACTED, text)


def make_scrubber(include_messages: bool) -> Callable[[Any, Any], Any]:
    """Build the ``before_send`` hook.

    Always dropped: request details, user, extra data, breadcrumbs and frame variables.
    Exception messages can carry personal data or secrets (a database error echoing
    parameters, a provider error echoing an address), so by default only the exception
    type is sent; with ``SENTRY_INCLUDE_EXCEPTION_MESSAGES`` the message is sent after
    ``redact``. Log messages (``logentry``) are always redacted.
    """

    def scrub_event(event: Any, hint: Any) -> Any:
        for key in ("request", "user", "extra", "breadcrumbs"):
            event.pop(key, None)
        for exception in event.get("exception", {}).get("values", []):
            if include_messages and isinstance(exception.get("value"), str):
                exception["value"] = redact(exception["value"])
            else:
                exception.pop("value", None)
            for frame in exception.get("stacktrace", {}).get("frames", []):
                frame.pop("vars", None)
        entry = event.get("logentry")
        if isinstance(entry, dict):
            for field in ("message", "formatted"):
                if isinstance(entry.get(field), str):
                    entry[field] = redact(entry[field])
            entry.pop("params", None)
        if isinstance(event.get("message"), str):
            event["message"] = redact(event["message"])
        return event

    return scrub_event


# Default behaviour (messages dropped), for callers that do not need the flag.
scrub_event = make_scrubber(False)


def release_name(config: Settings) -> str:
    if config.sentry_release:
        return config.sentry_release
    try:
        return f"api@{version('api')}"
    except PackageNotFoundError:
        return "api@unknown"


def init_sentry(config: Settings, service: str) -> bool:
    """Initialise Sentry for ``service`` ("api" or "worker"). False without a DSN."""
    dsn = secret_value(config.sentry_dsn)
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        release=release_name(config),
        environment=config.env,
        # Sentry 3 replaced send_default_pii with data_collection: switch every
        # personal-data category off, whatever an integration would otherwise attach.
        data_collection={
            "user_info": False,
            "cookies": {"mode": "off"},
            "http_headers": {"request": {"mode": "off"}},
            "http_bodies": [],
            "url_query_params": {"mode": "off"},
            "database_query_data": False,
            "queues": False,
            "stack_frame_variables": False,
        },
        max_request_body_size="never",
        traces_sample_rate=config.sentry_traces_sample_rate,
        before_send=make_scrubber(config.sentry_include_exception_messages),
        max_breadcrumbs=0,
    )
    sentry_sdk.set_tag("service", service)
    return True
