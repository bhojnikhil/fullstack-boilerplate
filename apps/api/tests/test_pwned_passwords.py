"""Optional breached-password check (Have I Been Pwned range API, mocked)."""

import hashlib

import httpx
import pytest
from sqlalchemy import func, select

from app.core.logging import configure_logging
from app.integrations.pwned_passwords import BreachedPasswordChecker
from app.modules.auth.models import User
from tests.conftest import TEST_PASSWORD
from tests.test_http_contract import assert_error

BREACHED = "password-from-a-breach"


def range_api(requests: list[httpx.Request]) -> httpx.MockTransport:
    digest = hashlib.sha1(BREACHED.encode()).hexdigest().upper()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        lines = ["0" * 35 + ":3", digest[5:] + ":42", "F" * 35 + ":0"]
        if not request.url.path.endswith(digest[:5]):
            lines = [digest[5:] + ":0"]  # Padding entries have a zero count.
        return httpx.Response(200, text="\r\n".join(lines))

    return httpx.MockTransport(handler)


async def test_only_a_hash_prefix_is_sent():
    requests: list[httpx.Request] = []
    checker = BreachedPasswordChecker(range_api(requests))
    assert await checker.is_breached(BREACHED) is True
    assert await checker.is_breached("a-password-nobody-has-used-9f2c") is False
    first = requests[0]
    prefix = hashlib.sha1(BREACHED.encode()).hexdigest().upper()[:5]
    assert str(first.url) == f"https://api.pwnedpasswords.com/range/{prefix}"
    assert first.headers["Add-Padding"] == "true"
    assert BREACHED not in str(first.url)


async def test_outage_fails_open_with_a_warning(capsys):
    configure_logging("test")

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("down", request=request)

    checker = BreachedPasswordChecker(httpx.MockTransport(down))
    assert await checker.is_breached(BREACHED) is False
    assert "password_breach_check_unavailable" in capsys.readouterr().err


@pytest.fixture
def breach_check(app):
    app.state.breach_checker = BreachedPasswordChecker(range_api([]))


async def test_register_rejects_breached_passwords(client, outbox, session_factory, breach_check):
    response = await client.post(
        "/v1/auth/register",
        json={"email": "new@example.com", "password": BREACHED, "name": "New"},
    )
    assert_error(response, 422, "password_breached")
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0
    assert outbox == []


async def test_password_changes_reject_breached_passwords(
    client, outbox, auth_headers, breach_check
):
    change = await client.post(
        "/v1/me/password",
        json={"current_password": TEST_PASSWORD, "new_password": BREACHED},
        headers=auth_headers,
    )
    assert_error(change, 422, "password_breached")

    await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    token = outbox[-1].text.split("#token=")[1].split()[0]
    reset = await client.post(
        "/v1/auth/password/reset", json={"token": token, "new_password": BREACHED}
    )
    assert_error(reset, 422, "password_breached")
    # The token was not consumed by the rejected attempt.
    retry = await client.post(
        "/v1/auth/password/reset", json={"token": token, "new_password": "a-fine-new-password-1"}
    )
    assert retry.status_code == 204


def test_disabled_by_default(app, config, session_factory):
    from app.factory import create_app

    assert config.password_breach_check is False
    assert app.state.breach_checker is None
    enabled = create_app(config.model_copy(update={"password_breach_check": True}), session_factory)
    assert isinstance(enabled.state.breach_checker, BreachedPasswordChecker)
