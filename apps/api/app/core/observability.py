"""Sentry, enabled only when SENTRY_DSN is set. Nothing is imported or sent otherwise."""

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from app.core.config import Settings, secret_value

SENSITIVE_EVENT_KEYS = ("request", "user", "extra", "contexts")


def scrub_event(event: Any, hint: Any) -> Any:
    """Drop what could carry personal data: request details, users and local variables.

    Exceptions, stack frames (without variable values), the release and the environment
    are kept.
    """
    for key in ("request", "user", "extra"):
        event.pop(key, None)
    for exception in event.get("exception", {}).get("values", []):
        for frame in exception.get("stacktrace", {}).get("frames", []):
            frame.pop("vars", None)
    event.pop("breadcrumbs", None)
    return event


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
        before_send=scrub_event,
        max_breadcrumbs=0,
    )
    sentry_sdk.set_tag("service", service)
    return True
