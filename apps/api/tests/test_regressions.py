"""Regression tests for the verified security defects 1-6 in the v2 spec.

Each test names the defect and what the code before the auth redesign did. The PR
description maps every defect to its fix and these tests.
"""

import hmac
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import jwt
import pytest
from sqlalchemy import select, text

from app.core.config import LOCAL_SECRET, Settings
from app.core.ratelimit import Rule
from app.core.security import InvalidAccessTokenError, create_access_token, decode_access_token
from app.integrations.google_id_token import CERTS_URL, GoogleIdTokenVerifier, GoogleTokenError
from app.modules.auth.models import User
from tests.conftest import TEST_PASSWORD
from tests.test_http_contract import assert_error
from tests.test_routers.test_auth import MOBILE, WEB, login, token_from

APP_DIR = Path(__file__).resolve().parents[1] / "app"


# --------------------------------------------------------------------------- defect 1
# GET /auth/google/callback accepted any `code` and never checked `state` (login CSRF).


async def test_defect1_redirect_flow_and_unverified_state_are_gone(client, app):
    for path in ("/v1/auth/google/login", "/v1/auth/google/callback?code=c&state=s"):
        assert_error(await client.get(path), 404, "not_found")
    paths = app.openapi()["paths"]
    assert not any("callback" in path or path.endswith("/google/login") for path in paths)


async def test_defect1_cross_site_requests_cannot_sign_a_browser_in(client, google):
    token = google.issue()
    cross_site = {"X-Platform": "web", "Origin": "https://evil.example"}
    response = await client.post("/v1/auth/google", json={"id_token": token}, headers=cross_site)
    assert_error(response, 403, "csrf_failed")
    assert "set-cookie" not in response.headers
    # A plain HTML form cannot send JSON, so it cannot reach the endpoint either.
    form = await client.post(
        "/v1/auth/google",
        content=f'{{"id_token": "{token}"}}',
        headers={"Content-Type": "text/plain", "X-Platform": "web", "Origin": WEB["Origin"]},
    )
    assert_error(form, 422, "validation_error")


# --------------------------------------------------------------------------- defect 2
# _find_or_create_user linked a Google identity to any user with the same email, so an
# attacker who pre-registered the victim's email kept access after a Google sign-in.


async def test_defect2_pre_registration_cannot_capture_the_account(client, google, outbox):
    attacker_password = "attacker-chosen-password"
    owner_password = "the-real-owners-password"
    address = "victim@example.com"
    await client.post(
        "/v1/auth/register",
        json={"email": address, "password": attacker_password, "name": "Attacker"},
    )
    attacker_link = token_from(outbox[-1])
    # No usable password before the inbox is proven, so no attacker sessions either.
    assert_error(
        await login(client, email=address, password=attacker_password), 401, "invalid_credentials"
    )
    # The owner opening that link cannot activate a password they did not choose.
    clicked = await client.post(
        "/v1/auth/verify-email", json={"token": attacker_link, "password": owner_password}
    )
    assert_error(clicked, 401, "invalid_credentials")

    # The owner registers: the newest pending password replaces the attacker's.
    await client.post(
        "/v1/auth/register", json={"email": address, "password": owner_password, "name": "Owner"}
    )
    owner_link = token_from(outbox[-1])
    verified = await client.post(
        "/v1/auth/verify-email", json={"token": owner_link, "password": owner_password}
    )
    assert verified.status_code == 204
    for token in (attacker_link, owner_link):
        dead = await client.post(
            "/v1/auth/verify-email", json={"token": token, "password": attacker_password}
        )
        assert_error(dead, 400, "invalid_or_expired_token")
    assert_error(
        await login(client, email=address, password=attacker_password), 401, "invalid_credentials"
    )
    assert (await login(client, email=address, password=owner_password)).status_code == 200

    # Google then links automatically to the owner's verified account.
    signed_in = await client.post(
        "/v1/auth/google",
        json={"id_token": google.issue(subject="owner-google", email=address)},
        headers=MOBILE,
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["sign_in_methods"] == ["password", "google"]


async def test_defect2_google_sign_in_claims_a_pre_registered_address(
    client, google, outbox, session_factory
):
    attacker_password = "attacker-chosen-password"
    await client.post(
        "/v1/auth/register",
        json={"email": "victim@gmail.com", "password": attacker_password, "name": "Attacker"},
    )
    attacker_link = token_from(outbox[-1])
    signed_in = await client.post(
        "/v1/auth/google",
        json={"id_token": google.issue(subject="victim-google", email="victim@gmail.com")},
        headers=MOBILE,
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["sign_in_methods"] == ["google"]
    # Google proved the inbox, so the attacker's pending password is gone for good.
    late = await client.post(
        "/v1/auth/verify-email", json={"token": attacker_link, "password": attacker_password}
    )
    assert_error(late, 400, "invalid_or_expired_token")
    assert_error(
        await login(client, email="victim@gmail.com", password=attacker_password),
        401,
        "invalid_credentials",
    )


async def test_defect2_registration_does_not_verify_email(client, session_factory):
    await client.post(
        "/v1/auth/register",
        json={"email": "new@example.com", "password": "long-enough-password", "name": "N"},
    )
    async with session_factory() as session:
        user = await session.scalar(select(User))
    assert user.email_verified_at is None


# --------------------------------------------------------------------------- defect 3
# The callback redirected to {frontend}/auth/callback?token=<JWT> (history, logs, Referer).


async def test_defect3_tokens_never_appear_in_urls(client, google, outbox, test_user):
    for headers in (MOBILE, WEB):
        response = await client.post(
            "/v1/auth/google", json={"id_token": google.issue()}, headers=headers
        )
        assert response.status_code == 200
        assert "location" not in response.headers
        assert response.headers["content-type"] == "application/json"
    await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    # Emailed tokens use the URL fragment, which browsers never send to a server.
    assert "#token=" in outbox[-1].text
    assert "?token=" not in outbox[-1].text + outbox[-1].html


# --------------------------------------------------------------------------- defect 4
# SECRET_KEY defaulted to a public value. Phase 3 made SECRET_KEY fail fast; the
# separate access-token key added here must fail fast too, and differ from it.


@pytest.mark.parametrize("jwt_secret", [None, LOCAL_SECRET, "short"])
def test_defect4_production_requires_its_own_jwt_secret(jwt_secret):
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(
            _env_file=None,
            env="production",
            secret_key="production-secret-" * 3,
            jwt_secret_key=jwt_secret,
            database_url="postgresql://app:app@db.example/app",
            email_backend="smtp",
            smtp_security="starttls",
            web_url="https://web.example",
        )


def test_defect4_tokens_signed_with_a_development_key_are_rejected(config):
    production = Settings(
        _env_file=None,
        env="production",
        secret_key="production-secret-" * 3,
        jwt_secret_key="production-jwt-secret-" * 3,
        database_url="postgresql://app:app@db.example/app",
        email_backend="smtp",
        smtp_security="starttls",
        web_url="https://web.example",
    )
    development = Settings(_env_file=None, env="development", secret_key=LOCAL_SECRET)
    assert not hmac.compare_digest(production.jwt_key, development.jwt_key)
    forged, _ = create_access_token(uuid.uuid4(), uuid.uuid4(), development)
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(forged, production)


# --------------------------------------------------------------------------- defect 5
# Access JWTs lived 7 days, nothing could revoke them, and login/register were unlimited.


async def test_defect5_access_tokens_are_short_lived(client, test_user):
    body = (await login(client)).json()
    assert body["expires_in"] == 15 * 60
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 15 * 60
    assert Settings.model_fields["access_token_expire_minutes"].default == 15


async def test_defect5_sign_out_ends_the_session_immediately(client, test_user):
    body = (await login(client)).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert (await client.post("/v1/auth/logout", headers=headers)).status_code == 204
    assert_error(await client.get("/v1/me", headers=headers), 401, "invalid_token")
    refresh = await client.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert_error(refresh, 401, "invalid_refresh_token")


async def test_defect5_login_and_register_are_rate_limited(client, app, test_user):
    limiter = app.state.rate_limiter
    limiter.overrides["login_ip"] = Rule("login_ip", 3, timedelta(minutes=15))
    limiter.overrides["register_ip"] = Rule("register_ip", 3, timedelta(hours=1))
    statuses = [(await login(client, password="wrong")).status_code for _ in range(4)]
    assert statuses == [401, 401, 401, 429]
    payload = {"password": "long-enough-password", "name": "N"}
    statuses = [
        (
            await client.post("/v1/auth/register", json={**payload, "email": f"r{i}@x.com"})
        ).status_code
        for i in range(4)
    ]
    assert statuses == [202, 202, 202, 429]
    assert (await login(client, password=TEST_PASSWORD)).status_code == 429


# --------------------------------------------------------------------------- defect 6
# Google access/refresh tokens were requested (access_type=offline, prompt=consent) and
# stored in plaintext in oauth_accounts.


async def test_defect6_no_provider_token_columns(test_db):
    columns = await test_db.scalars(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'oauth_accounts'"
        )
    )
    assert not {"access_token", "refresh_token", "expires_at"} & set(columns)


async def test_defect6_google_sign_in_only_fetches_public_certificates():
    requests: list[httpx.Request] = []

    def google(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"kid": "not-a-real-certificate"})

    verifier = GoogleIdTokenVerifier(
        ["web.apps.googleusercontent.com"], transport=httpx.MockTransport(google)
    )
    with pytest.raises(GoogleTokenError):
        await verifier.verify("eyJhbGciOiJSUzI1NiIsImtpZCI6ImtpZCJ9.e30.c2ln")
    assert [(r.method, str(r.url)) for r in requests] == [("GET", CERTS_URL)]


def test_defect6_no_code_requests_offline_google_access():
    source = "\n".join(path.read_text() for path in APP_DIR.rglob("*.py"))
    for marker in ("access_type", "prompt=consent", "oauth2.googleapis.com/token", "userinfo"):
        assert marker not in source
