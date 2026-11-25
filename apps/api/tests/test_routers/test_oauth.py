from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.modules.auth import oauth
from app.modules.auth.models import OAuthAccount, User
from tests.test_http_contract import assert_error


@pytest.fixture
def config(config):
    config.google_client_id = "fake-client-id"
    config.google_client_secret = SecretStr("fake-client-secret")
    return config


def mock_google(monkeypatch, handler):
    def client(*args, **kwargs):
        assert kwargs["timeout"].connect == 2
        assert kwargs["timeout"].read == 5
        return httpx.AsyncClient(*args, **kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(oauth, "AsyncClient", client)


async def test_google_redirect_and_account_persist(client, monkeypatch, config, session_factory):
    def google(request):
        assert request.headers["X-Request-Id"] == "google-flow-42"
        if request.method == "POST":
            assert parse_qs(request.content.decode())["redirect_uri"] == [
                str(config.google_redirect_uri)
            ]
            return httpx.Response(
                200, json={"access_token": "fake-access", "refresh_token": "fake-refresh"}
            )
        assert request.headers["Authorization"] == "Bearer fake-access"
        return httpx.Response(200, json={"id": "provider-id", "email": "google@example.com"})

    mock_google(monkeypatch, google)
    response = await client.get("/v1/auth/google/login")
    assert response.status_code == 200
    data = response.json()
    query = parse_qs(urlsplit(data["authorization_url"]).query)
    assert query["state"] == [data["state"]]
    assert query["redirect_uri"] == [str(config.google_redirect_uri)]

    for _ in range(2):
        callback = await client.get(
            "/v1/auth/google/callback?code=fake-code", headers={"X-Request-Id": "google-flow-42"}
        )
        assert callback.status_code == 307
        location = urlsplit(callback.headers["location"])
        assert location.path == "/auth/callback"
        token = parse_qs(location.query)["token"][0]
        user = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert user.status_code == 200
        assert user.json()["email"] == "google@example.com"

    async with session_factory() as session:
        accounts = (await session.scalars(select(OAuthAccount))).all()
        assert len(accounts) == 1
        assert accounts[0].access_token == "fake-access"
        assert accounts[0].refresh_token == "fake-refresh"


async def test_google_links_existing_account(client, monkeypatch, test_user, session_factory):
    def google(request):
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "fake-access"})
        return httpx.Response(200, json={"id": "provider-id", "email": test_user.email})

    mock_google(monkeypatch, google)
    callback = await client.get("/v1/auth/google/callback?code=fake-code")
    assert callback.status_code == 307
    async with session_factory() as session:
        account = (await session.scalars(select(OAuthAccount))).one()
        assert account.user_id == test_user.id


@pytest.mark.parametrize("failure", ["timeout", "rejected", "bad-json"])
async def test_google_failure_is_sanitized(client, monkeypatch, failure):
    def google(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("provider-private-message", request=request)
        if failure == "rejected":
            return httpx.Response(400, text="provider-private-message")
        return httpx.Response(200, text="provider-private-message")

    mock_google(monkeypatch, google)
    response = await client.get("/v1/auth/google/callback?code=fake-code")
    assert_error(response, 400, "oauth_failed")
    assert "provider-private-message" not in response.text


async def test_google_account_write_failure_rolls_back_user(client, monkeypatch, session_factory):
    def google(request):
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "fake-access"})
        # The provider account ID exceeds the database column limit.
        return httpx.Response(200, json={"id": "x" * 256, "email": "google@example.com"})

    mock_google(monkeypatch, google)
    response = await client.get("/v1/auth/google/callback?code=fake-code")
    assert_error(response, 500, "internal_error")
    async with session_factory() as session:
        assert await session.scalar(select(User)) is None
        assert await session.scalar(select(OAuthAccount)) is None
