"""Resend and Expo HTTP clients (mock transports) and the Sentry gate."""

import json

import httpx
import pytest
import sentry_sdk
from pydantic import ValidationError

from app.core.config import Settings
from app.core.observability import init_sentry, scrub_event
from app.integrations.email import (
    Email,
    EmailDeliveryError,
    ResendEmailBackend,
    build_email_backend,
)
from app.integrations.email.templates import Template
from app.integrations.push import (
    DEVICE_NOT_REGISTERED,
    ExpoPushBackend,
    LogPushBackend,
    MemoryPushBackend,
    PushMessage,
    PushUnavailableError,
    build_push_backend,
)

EMAIL = Email(Template.EMAIL_CHANGED, "person@example.com", "Subject", "text", "<p>html</p>")


def settings(**overrides) -> Settings:
    fields = {
        "env": "test",
        "database_url": "postgresql://u:p@localhost/db",
        "secret_key": "k" * 40,
    }
    return Settings(_env_file=None, **{**fields, **overrides})


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_resend_posts_the_message_with_an_idempotency_key():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "abc"})

    config = settings(
        email_backend="resend", resend_api_key="re_test_key", email_from="App <a@x.io>"
    )
    await ResendEmailBackend(config, mock_client(handler)).send(EMAIL, key="job-1")
    [request] = seen
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer re_test_key"
    assert request.headers["idempotency-key"] == "job-1"
    assert json.loads(request.content) == {
        "from": "App <a@x.io>",
        "to": ["person@example.com"],
        "subject": "Subject",
        "text": "text",
        "html": "<p>html</p>",
    }


@pytest.mark.parametrize("status", [400, 401, 429, 500])
async def test_resend_failures_raise_without_the_response_body(status):
    def handler(request):
        return httpx.Response(status, json={"message": "person@example.com is suppressed"})

    backend = ResendEmailBackend(
        settings(email_backend="resend", resend_api_key="k"), mock_client(handler)
    )
    with pytest.raises(EmailDeliveryError) as error:
        await backend.send(EMAIL)
    assert str(error.value) == f"http_{status}"


async def test_resend_network_errors_are_wrapped():
    def handler(request):
        raise httpx.ConnectTimeout("timed out talking to person@example.com")

    backend = ResendEmailBackend(
        settings(email_backend="resend", resend_api_key="k"), mock_client(handler)
    )
    with pytest.raises(EmailDeliveryError) as error:
        await backend.send(EMAIL)
    assert str(error.value) == "ConnectTimeout"
    await backend.aclose()


def test_backend_selection_and_settings_validation():
    assert isinstance(
        build_email_backend(settings(email_backend="resend", resend_api_key="k")),
        ResendEmailBackend,
    )
    with pytest.raises(ValidationError, match="RESEND_API_KEY"):
        settings(email_backend="resend")
    deployed = {
        "env": "production",
        "jwt_secret_key": "j" * 40,
        "web_url": "https://web.example.com",
        "rate_limit_backend": "postgres",
        "email_backend": "resend",
        "resend_api_key": "k",
        "trusted_hosts": ["api.example.com"],
    }
    assert settings(**deployed).email_backend == "resend"
    # Phase 4's rule is unchanged: authenticated SMTP needs TLS outside development.
    with pytest.raises(ValidationError, match="SMTP_SECURITY"):
        settings(**{**deployed, "email_backend": "smtp"})
    with pytest.raises(ValidationError, match="credentials require"):
        settings(
            **{**deployed, "email_backend": "smtp", "smtp_username": "u", "smtp_password": "p"}
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"storage_backend": "s3"},
        {
            "storage_backend": "s3",
            "storage_endpoint_url": "https://x.example",
            "storage_bucket": "b",
        },
        {"min_supported_app_version": "latest"},
        {"latest_app_version": "1.2.3.4"},
        {"storage_allowed_content_types": ["image/*"]},
        {"job_timeout_seconds": 300, "job_lock_timeout_seconds": 300},
    ],
)
def test_new_settings_are_validated(overrides):
    with pytest.raises(ValidationError):
        settings(**overrides)


def test_s3_endpoint_must_be_https_when_deployed():
    s3 = {
        "storage_backend": "s3",
        "storage_endpoint_url": "http://minio.internal:9000",
        "storage_bucket": "b",
        "storage_access_key_id": "id",
        "storage_secret_access_key": "secret",
    }
    assert settings(**s3).storage_backend == "s3"
    with pytest.raises(ValidationError, match="https"):
        settings(
            **s3,
            env="staging",
            jwt_secret_key="j" * 40,
            web_url="https://web.example.com",
            email_backend="resend",
            resend_api_key="k",
            rate_limit_backend="postgres",
            trusted_hosts=["api.example.com"],
        )


async def test_expo_sends_in_chunks_and_parses_tickets():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append((str(request.url), request.headers.get("authorization"), body))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"status": "error", "details": {"error": DEVICE_NOT_REGISTERED}}
                    if message["to"].endswith("[bad]")
                    else {"status": "ok", "id": f"id-{index}"}
                    for index, message in enumerate(body)
                ]
            },
        )

    backend = ExpoPushBackend(
        settings(push_backend="expo", expo_access_token="secret"), mock_client(handler)
    )
    messages = [PushMessage(f"ExponentPushToken[t{n}]", "T", "B", {"n": n}) for n in range(150)]
    messages[3] = PushMessage("ExponentPushToken[bad]", "T", "B")
    tickets = await backend.send(messages)
    assert [len(body) for _, _, body in requests] == [100, 50]
    assert requests[0][0] == "https://exp.host/--/api/v2/push/send"
    assert requests[0][2][0] == {
        "to": "ExponentPushToken[t0]",
        "title": "T",
        "body": "B",
        "data": {"n": 0},
        "sound": "default",
    }
    assert tickets[3].error == DEVICE_NOT_REGISTERED and tickets[3].id is None
    assert tickets[0].id == "id-0" and len(tickets) == 150


async def test_expo_receipts_are_chunked_and_parsed():
    def handler(request: httpx.Request) -> httpx.Response:
        ids = json.loads(request.content)["ids"]
        return httpx.Response(
            200,
            json={
                "data": {
                    ids[0]: {"status": "error", "details": {"error": DEVICE_NOT_REGISTERED}},
                    **{i: {"status": "ok"} for i in ids[1:]},
                }
            },
        )

    backend = ExpoPushBackend(settings(push_backend="expo"), mock_client(handler))
    found = await backend.receipts([f"t{n}" for n in range(1500)])
    assert len(found) == 1500
    assert found["t0"].error == DEVICE_NOT_REGISTERED and not found["t0"].ok
    assert found["t1"].ok
    await backend.aclose()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={}),
        httpx.Response(429, json={}),
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json=[1]),
        httpx.Response(200, json={"data": []}),
        httpx.Response(200, json={"data": "x"}),
    ],
)
async def test_expo_outages_and_bad_responses_raise_for_retry(response):
    backend = ExpoPushBackend(settings(), mock_client(lambda request: response))
    with pytest.raises(PushUnavailableError):
        await backend.send([PushMessage("ExponentPushToken[a]", "t", "b")])
    with pytest.raises(PushUnavailableError):
        await backend.receipts(["a"])


async def test_expo_network_errors_are_wrapped():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    backend = ExpoPushBackend(settings(), mock_client(handler))
    with pytest.raises(PushUnavailableError, match="ReadTimeout"):
        await backend.send([PushMessage("ExponentPushToken[a]", "t", "b")])


async def test_unparseable_tickets_and_receipts_count_as_errors():
    def handler(request):
        if "getReceipts" in str(request.url):
            return httpx.Response(200, json={"data": {"a": "garbage", "b": {"status": "error"}}})
        return httpx.Response(200, json={"data": ["garbage", {"status": "error", "message": "x"}]})

    backend = ExpoPushBackend(settings(), mock_client(handler))
    tickets = await backend.send([PushMessage("ExponentPushToken[a]", "t", "b")] * 2)
    assert [t.error for t in tickets] == ["unknown_error", "unknown_error"]
    found = await backend.receipts(["a", "b"])
    assert [r.error for r in found.values()] == ["unknown_error", "unknown_error"]


async def test_expo_access_token_is_sent_as_a_bearer_header():
    backend = ExpoPushBackend(settings(push_backend="expo", expo_access_token="tok"))
    assert backend.client.headers["authorization"] == "Bearer tok"
    await backend.aclose()


async def test_push_backend_selection_and_fakes(capsys):
    assert isinstance(build_push_backend(settings()), LogPushBackend)
    assert isinstance(build_push_backend(settings(push_backend="memory")), MemoryPushBackend)
    assert isinstance(build_push_backend(settings(push_backend="expo")), ExpoPushBackend)
    log_backend = LogPushBackend()
    message = PushMessage("ExponentPushToken[secret-token]", "Secret title", "Secret body")
    assert len(await log_backend.send([message])) == 1
    assert await log_backend.receipts(["a"]) == {}
    memory = MemoryPushBackend()
    memory.fail_with = PushUnavailableError("x")
    with pytest.raises(PushUnavailableError):
        await memory.receipts(["a"])
    assert "secret" not in capsys.readouterr().out.lower()


def test_sentry_is_a_noop_without_a_dsn(monkeypatch):
    monkeypatch.setattr(sentry_sdk, "init", lambda **_: pytest.fail("initialised without a DSN"))
    assert init_sentry(settings(), "api") is False
    assert init_sentry(settings(sentry_dsn=""), "worker") is False


def test_sentry_init_sets_release_environment_and_no_personal_data(monkeypatch):
    captured = {}
    tags = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(sentry_sdk, "set_tag", lambda key, value: tags.update({key: value}))
    config = settings(
        sentry_dsn="https://public@o0.ingest.sentry.io/1",
        sentry_release="api@9.9.9",
        sentry_traces_sample_rate=0.25,
        env="staging",
        jwt_secret_key="j" * 40,
        web_url="https://web.example.com",
        email_backend="resend",
        resend_api_key="k",
        trusted_hosts=["api.example.com"],
    )
    assert init_sentry(config, "worker") is True
    assert captured["dsn"] == "https://public@o0.ingest.sentry.io/1"
    assert (captured["release"], captured["environment"]) == ("api@9.9.9", "staging")
    assert captured["traces_sample_rate"] == 0.25
    assert captured["max_request_body_size"] == "never"
    collection = captured["data_collection"]
    assert collection["user_info"] is False
    assert collection["http_bodies"] == []
    assert collection["cookies"] == {"mode": "off"}
    assert collection["http_headers"] == {"request": {"mode": "off"}}
    assert collection["stack_frame_variables"] is False
    assert captured["max_breadcrumbs"] == 0
    assert tags == {"service": "worker"}
    # Default release is derived from the package version.
    default = settings(sentry_dsn="https://public@o0.ingest.sentry.io/1")
    init_sentry(default, "api")
    assert captured["release"].startswith("api@")


def test_scrub_event_drops_request_user_and_local_variables():
    event = {
        "request": {"data": {"password": "x"}, "headers": {"Authorization": "Bearer t"}},
        "user": {"email": "person@example.com"},
        "extra": {"k": "v"},
        "breadcrumbs": [{"message": "m"}],
        "exception": {
            "values": [
                {"type": "E", "stacktrace": {"frames": [{"function": "f", "vars": {"p": "x"}}]}}
            ]
        },
        "release": "api@1",
        "environment": "production",
    }
    scrubbed = scrub_event(event, {})
    assert scrubbed == {
        "exception": {"values": [{"type": "E", "stacktrace": {"frames": [{"function": "f"}]}}]},
        "release": "api@1",
        "environment": "production",
    }


def test_a_real_sentry_client_reports_errors_without_personal_data():
    from sentry_sdk.transport import Transport

    events = []

    class Capture(Transport):
        def capture_envelope(self, envelope):
            for item in envelope.items:
                if item.type == "event":
                    events.append(item.payload.json)

    config = settings(sentry_dsn="https://public@o0.ingest.sentry.io/1", sentry_release="api@1.2.3")
    try:
        init_sentry(config, "api")
        client = sentry_sdk.get_client()
        client.transport = Capture({})
        client.options["transport"] = client.transport
        password = "-".join(["hunter", "2"])  # built at runtime: only a frame variable holds it
        try:
            raise ValueError(password[:0] + "bad input")
        except ValueError:
            sentry_sdk.capture_exception()
        sentry_sdk.flush()
    finally:
        sentry_sdk.get_client().close()
    [event] = events
    assert (event["release"], event["environment"]) == ("api@1.2.3", "test")
    assert event["tags"]["service"] == "api"
    assert "request" not in event and "user" not in event
    frames = event["exception"]["values"][0]["stacktrace"]["frames"]
    assert all("vars" not in frame for frame in frames)
    assert "hunter2" not in json.dumps(event)
