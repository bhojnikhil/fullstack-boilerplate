"""Email/password accounts: registration, sign-in, refresh, sessions, verification, reset."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from http.cookies import Morsel, SimpleCookie

import bcrypt
import jwt
import pytest
from sqlalchemy import select, update

from app.core.audit import AuditEvent
from app.core.ratelimit import Rule
from app.integrations.email.templates import Template
from app.modules.auth.cookies import CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE, REFRESH_PATH
from app.modules.auth.models import AccountToken, AuthSession, SessionRevocation, User
from tests.conftest import TEST_PASSWORD, WEB_ORIGIN, bearer, create_user, sign_in
from tests.test_http_contract import assert_error

MOBILE = {"X-Platform": "android"}
WEB = {"X-Platform": "web", "Origin": WEB_ORIGIN}
NEW_PASSWORD = "a-brand-new-password-42"


def cookies(response) -> dict[str, Morsel[str]]:
    jar: SimpleCookie = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        jar.load(header)
    return dict(jar)


def token_from(email) -> str:
    return email.text.split("#token=")[1].split()[0]


async def audit_events(session_factory, event: str | None = None) -> list[AuditEvent]:
    statement = select(AuditEvent).order_by(AuditEvent.created_at)
    if event is not None:
        statement = statement.where(AuditEvent.event == event)
    async with session_factory() as session:
        return list(await session.scalars(statement))


async def reload(session_factory, model, identifier):
    async with session_factory() as session:
        return await session.get(model, identifier)


async def login(client, email="test@example.com", password=TEST_PASSWORD, headers=MOBILE, **body):
    return await client.post(
        "/v1/auth/login", json={"email": email, "password": password, **body}, headers=headers
    )


def web_refresh_headers(refresh_token: str, csrf_token: str, **extra: str) -> dict[str, str]:
    return {
        **WEB,
        "Cookie": f"{REFRESH_COOKIE}={refresh_token}; {CSRF_COOKIE}={csrf_token}",
        CSRF_HEADER: csrf_token,
        **extra,
    }


# --------------------------------------------------------------------------- register


async def test_register_creates_unverified_account_and_sends_link(
    client, outbox, session_factory, config
):
    response = await client.post(
        "/v1/auth/register",
        json={"email": " New.User@Example.COM ", "password": NEW_PASSWORD, "name": "New User"},
    )
    assert response.status_code == 202
    assert "access_token" not in response.json()

    async with session_factory() as session:
        user = await session.scalar(select(User))
    assert user.email == "new.user@example.com"
    assert user.email_verified_at is None
    # No usable password until the link is opened: it waits in the emailed token.
    assert user.hashed_password is None

    [email] = outbox
    assert email.template == Template.VERIFY_EMAIL
    assert email.to == "new.user@example.com"
    assert f"{config.web_url}auth/verify-email#token=" in email.text
    assert "New User" in email.html
    async with session_factory() as session:
        stored = await session.scalar(select(AccountToken))
    assert stored.token_hash != token_from(email)  # Only the digest is stored.
    assert stored.password_hash.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert [e.event for e in await audit_events(session_factory)] == ["account_registered"]
    # Not usable before verification.
    assert_error(
        await login(client, email="new.user@example.com", password=NEW_PASSWORD),
        401,
        "invalid_credentials",
    )


async def test_register_does_not_reveal_existing_accounts(
    client, outbox, session_factory, test_user
):
    unverified = await create_user(session_factory, email="pending@example.com", verified=False)
    await create_user(session_factory, email="disabled@example.com", is_active=False)
    payload = {"password": NEW_PASSWORD, "name": "Someone"}
    responses = [
        await client.post("/v1/auth/register", json={**payload, "email": email})
        for email in (
            "fresh@example.com",
            "TEST@example.com",
            "pending@example.com",
            "disabled@example.com",
        )
    ]
    assert {r.status_code for r in responses} == {202}
    assert len({r.text for r in responses}) == 1
    assert len({frozenset(r.headers.keys()) for r in responses}) == 1

    assert [(e.template, e.to) for e in outbox] == [
        (Template.VERIFY_EMAIL, "fresh@example.com"),
        (Template.ACCOUNT_EXISTS, "test@example.com"),
        (Template.VERIFY_EMAIL, "pending@example.com"),
    ]
    # Existing passwords are untouched.
    assert (await login(client)).status_code == 200
    assert (await reload(session_factory, User, unverified.id)).hashed_password is None


@pytest.mark.parametrize(
    ("body", "location"),
    [
        ({"password": "x" * 11}, "password"),
        ({"password": "x" * 129}, "password"),
        ({"email": "not-an-email"}, "email"),
        ({"name": "   "}, "name"),
        ({"name": "bad\nname"}, "name"),
    ],
)
async def test_register_validation(client, outbox, body, location):
    payload = {"email": "ok@example.com", "password": NEW_PASSWORD, "name": "Ok", **body}
    response = await client.post("/v1/auth/register", json=payload)
    error = assert_error(response, 422, "validation_error")
    assert ["body", location] in [field["location"] for field in error["details"]["fields"]]
    assert outbox == []


async def test_register_is_rate_limited_per_account_and_ip(client, app):
    payload = {"email": "flood@example.com", "password": NEW_PASSWORD, "name": "Flood"}
    for _ in range(3):
        assert (await client.post("/v1/auth/register", json=payload)).status_code == 202
    limited = await client.post("/v1/auth/register", json=payload)
    error = assert_error(limited, 429, "rate_limited")
    assert 3500 < int(limited.headers["retry-after"]) <= 3600
    assert error["details"]["retry_after"] == int(limited.headers["retry-after"])

    app.state.rate_limiter.overrides["register_ip"] = Rule("register_ip", 4, timedelta(hours=1))
    other = {**payload, "email": "other@example.com"}
    assert (await client.post("/v1/auth/register", json=other)).status_code == 429


# --------------------------------------------------------------------------- login


async def test_mobile_login_returns_tokens_in_body(client, config, session_factory, test_user):
    response = await login(
        client, device_name="Pixel 8", headers={**MOBILE, "User-Agent": "okhttp/4.12.0"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["refresh_token"] and body["csrf_token"] is None
    assert response.headers["cache-control"] == "no-store"
    assert body["user"]["email"] == "test@example.com"
    assert body["user"]["email_verified"] is True
    assert body["user"]["sign_in_methods"] == ["password"]
    assert "set-cookie" not in response.headers

    header = jwt.get_unverified_header(body["access_token"])
    claims = jwt.decode(
        body["access_token"],
        config.jwt_key,
        algorithms=["HS256"],
        audience=config.jwt_audience,
        issuer=config.jwt_issuer,
    )
    assert header["typ"] == "at+jwt"
    assert claims["sub"] == str(test_user.id)
    assert claims["exp"] - claims["iat"] == 15 * 60
    session = await reload(session_factory, AuthSession, uuid.UUID(claims["sid"]))
    assert (session.platform, session.device_name, session.sign_in_method) == (
        "android",
        "Pixel 8",
        "password",
    )
    assert session.user_agent == "Android app"
    assert session.ip_hash and "127.0.0.1" not in session.ip_hash

    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["id"] == str(test_user.id)


async def test_web_login_sets_refresh_cookie_and_returns_csrf_token(client, test_user):
    response = await login(client, headers=WEB)
    assert response.status_code == 200
    body = response.json()
    assert body["refresh_token"] is None
    jar = cookies(response)
    refresh, csrf = jar[REFRESH_COOKIE], jar[CSRF_COOKIE]
    assert csrf.value == body["csrf_token"]
    for cookie in (refresh, csrf):
        assert cookie["httponly"] and cookie["secure"]
        assert cookie["samesite"].lower() == "strict"
        assert cookie["path"] == REFRESH_PATH
        assert 29 * 86400 < int(cookie["max-age"]) <= 30 * 86400


@pytest.mark.parametrize("origin", [None, "https://evil.example", "http://localhost:3001"])
async def test_web_login_requires_an_allowed_origin(client, session_factory, test_user, origin):
    headers = {"X-Platform": "web", **({"Origin": origin} if origin else {})}
    assert_error(await login(client, headers=headers), 403, "csrf_failed")
    async with session_factory() as session:
        assert await session.scalar(select(AuthSession)) is None


async def test_development_cookies_are_not_secure(session_factory, config, test_user, google):
    from httpx import ASGITransport, AsyncClient

    from app.factory import create_app

    app = create_app(config.model_copy(update={"env": "development"}), session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as dev:
        response = await login(dev, headers=WEB)
    assert not cookies(response)[REFRESH_COOKIE]["secure"]


async def test_login_failures_do_not_reveal_accounts(client, session_factory, test_user):
    await create_user(session_factory, email="google-only@example.com")
    failures = [
        await login(client, password="wrong-password"),
        await login(client, email="nobody@example.com"),
        await login(client, email="google-only@example.com"),
    ]
    for response in failures:
        assert_error(response, 401, "invalid_credentials")
    assert len({response.text for response in failures}) == 1

    events = await audit_events(session_factory, "login_failed")
    assert [event.user_id is not None for event in events] == [True, False, True]
    for event in events:
        assert set(event.details) == {"method", "email_hash"}
        assert "@" not in str(event.details)


async def test_inactive_user_is_told_only_with_the_right_password(
    client, session_factory, test_user
):
    async with session_factory.begin() as session:
        await session.execute(update(User).values(is_active=False))
    assert_error(await login(client, password="wrong-password"), 401, "invalid_credentials")
    assert_error(await login(client), 403, "inactive_user")


async def test_email_is_case_insensitive(client, test_user):
    assert (await login(client, email="Test@EXAMPLE.com")).status_code == 200


async def test_repeated_failures_lock_the_account_identifier_with_backoff(client, app, test_user):
    backend = app.state.rate_limiter.backend
    for email in ("test@example.com", "nobody@example.com"):
        for _ in range(5):
            assert_error(
                await login(client, email=email, password="wrong-password"),
                401,
                "invalid_credentials",
            )
        # Locked for 30 seconds, even with the right password, whether or not it exists.
        locked = await login(client, email=email)
        assert_error(locked, 429, "rate_limited")
        assert 25 <= int(locked.headers["retry-after"]) <= 30

    real_clock = backend.clock
    backend.clock = lambda: real_clock() + timedelta(seconds=31)
    assert_error(await login(client, password="wrong-password"), 401, "invalid_credentials")
    # The sixth failure doubles the lockout.
    locked = await login(client)
    assert 55 <= int(locked.headers["retry-after"]) <= 60

    backend.clock = lambda: real_clock() + timedelta(seconds=95)
    assert (await login(client)).status_code == 200
    # Success clears the failure count: one more failure does not lock again.
    assert_error(await login(client, password="wrong-password"), 401, "invalid_credentials")
    assert (await login(client)).status_code == 200


async def test_login_is_rate_limited_per_ip(client, app, test_user):
    app.state.rate_limiter.overrides["login_ip"] = Rule("login_ip", 2, timedelta(minutes=15))
    assert (await login(client)).status_code == 200
    assert (await login(client)).status_code == 200
    assert_error(await login(client), 429, "rate_limited")


async def test_bcrypt_hash_is_upgraded_to_argon2id_on_login(client, session_factory):
    legacy = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()
    user = await create_user(session_factory, hashed_password=legacy)

    assert (await login(client)).status_code == 200
    upgraded = (await reload(session_factory, User, user.id)).hashed_password
    assert upgraded.startswith("$argon2id$")
    assert (await login(client)).status_code == 200
    assert (await reload(session_factory, User, user.id)).hashed_password == upgraded
    [first, second] = await audit_events(session_factory, "login_succeeded")
    assert (first.details["rehashed"], second.details["rehashed"]) == (True, False)


async def test_legacy_bcrypt_passwords_over_72_bytes_still_work(client, session_factory):
    password = "long-passphrase-" * 7  # 112 bytes; bcrypt 4.x hashed only the first 72.
    legacy = bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=4)).decode()
    await create_user(session_factory, hashed_password=legacy)

    assert (await login(client, password=password)).status_code == 200
    # The argon2id replacement covers the whole password.
    assert (await login(client, password=password[:72])).status_code == 401
    assert (await login(client, password=password)).status_code == 200


# --------------------------------------------------------------------------- refresh


async def test_refresh_rotates_and_reuse_revokes_the_session(client, session_factory, test_user):
    first = (await login(client)).json()
    rotated = await client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["access_token"] != first["access_token"]
    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {second['access_token']}"})
    assert me.status_code == 200

    # Replaying the first token: someone else has the session's tokens.
    replay = await client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert_error(replay, 401, "invalid_refresh_token")
    [event] = await audit_events(session_factory, "refresh_token_reused")
    session = await reload(session_factory, AuthSession, event.session_id)
    assert session.revoked_reason == SessionRevocation.REFRESH_TOKEN_REUSED

    # The whole family is dead: the newest refresh token and access token too.
    assert_error(
        await client.post("/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}),
        401,
        "invalid_refresh_token",
    )
    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {second['access_token']}"})
    assert_error(me, 401, "invalid_token")
    # Further replays are still recorded, and the original revocation reason is kept.
    replay = await client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert_error(replay, 401, "invalid_refresh_token")
    assert len(await audit_events(session_factory, "refresh_token_reused")) == 2
    session = await reload(session_factory, AuthSession, event.session_id)
    assert session.revoked_reason == SessionRevocation.REFRESH_TOKEN_REUSED


async def test_concurrent_refreshes_with_one_token_are_serialized(
    client, session_factory, test_user
):
    token = (await login(client)).json()["refresh_token"]
    responses = await asyncio.gather(
        *(client.post("/v1/auth/refresh", json={"refresh_token": token}) for _ in range(2))
    )
    assert sorted(response.status_code for response in responses) == [200, 401]
    async with session_factory() as session:
        [session_row] = await session.scalars(select(AuthSession))
    assert session_row.revoked_reason == SessionRevocation.REFRESH_TOKEN_REUSED


async def test_web_refresh_uses_cookie_with_csrf(client, test_user):
    signed_in = await login(client, headers=WEB)
    jar = cookies(signed_in)
    refresh, csrf = jar[REFRESH_COOKIE].value, jar[CSRF_COOKIE].value

    response = await client.post("/v1/auth/refresh", headers=web_refresh_headers(refresh, csrf))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["refresh_token"] is None
    assert body["csrf_token"] == csrf  # Bound to the session, so stable across refreshes.
    new_jar = cookies(response)
    assert new_jar[REFRESH_COOKIE].value != refresh
    assert new_jar[CSRF_COOKIE].value == csrf


@pytest.mark.parametrize(
    "tamper",
    [
        {CSRF_HEADER: ""},
        {CSRF_HEADER: "wrong-token"},
        {"Origin": "https://evil.example"},
        {"Origin": ""},
    ],
)
async def test_web_refresh_rejects_csrf_without_changing_state(client, test_user, tamper):
    jar = cookies(await login(client, headers=WEB))
    refresh, csrf = jar[REFRESH_COOKIE].value, jar[CSRF_COOKIE].value
    headers = {k: v for k, v in web_refresh_headers(refresh, csrf, **tamper).items() if v}

    rejected = await client.post("/v1/auth/refresh", headers=headers)
    assert_error(rejected, 403, "csrf_failed")
    assert "set-cookie" not in rejected.headers  # Another site cannot sign the user out.
    # Nothing was rotated: the cookie still works.
    ok = await client.post("/v1/auth/refresh", headers=web_refresh_headers(refresh, csrf))
    assert ok.status_code == 200


async def test_web_refresh_rejects_a_forged_matching_cookie_and_header(client, test_user):
    jar = cookies(await login(client, headers=WEB))
    forged = "attacker-chosen-csrf-value"
    response = await client.post(
        "/v1/auth/refresh", headers=web_refresh_headers(jar[REFRESH_COOKIE].value, forged)
    )
    assert_error(response, 403, "csrf_failed")


@pytest.mark.parametrize("cookie", [None, "not-a-real-refresh-token-value"])
async def test_web_refresh_without_a_valid_cookie_clears_it(client, cookie):
    headers = {**WEB, **({"Cookie": f"{REFRESH_COOKIE}={cookie}"} if cookie else {})}
    response = await client.post("/v1/auth/refresh", headers=headers)
    assert_error(response, 401, "invalid_refresh_token")
    if cookie:
        jar = cookies(response)
        assert jar[REFRESH_COOKIE]["max-age"] == "0"
        assert jar[CSRF_COOKIE]["max-age"] == "0"


async def test_refresh_rejects_expired_and_revoked_sessions(client, session_factory, test_user):
    for column in ("expires_at", "revoked_at"):
        token = (await login(client)).json()["refresh_token"]
        async with session_factory.begin() as session:
            await session.execute(
                update(AuthSession)
                .where(AuthSession.revoked_at.is_(None))
                .values({column: datetime.now(UTC) - timedelta(seconds=1)})
            )
        response = await client.post("/v1/auth/refresh", json={"refresh_token": token})
        assert_error(response, 401, "invalid_refresh_token")


async def test_refresh_slides_expiry_up_to_the_absolute_limit(
    client, session_factory, config, test_user
):
    token = (await login(client)).json()["refresh_token"]
    created = datetime.now(UTC) - timedelta(days=config.session_max_age_days - 1)
    async with session_factory.begin() as session:
        await session.execute(update(AuthSession).values(created_at=created))
    response = await client.post("/v1/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 200
    async with session_factory() as session:
        row = await session.scalar(select(AuthSession))
    assert row.expires_at == created + timedelta(days=config.session_max_age_days)


async def test_refresh_for_inactive_user(client, session_factory, test_user):
    token = (await login(client)).json()["refresh_token"]
    async with session_factory.begin() as session:
        await session.execute(update(User).values(is_active=False))
    response = await client.post("/v1/auth/refresh", json={"refresh_token": token})
    assert_error(response, 403, "inactive_user")


@pytest.mark.parametrize("body", [{"refresh_token": "short"}, {"refresh_token": "x" * 43, "x": 1}])
async def test_refresh_body_validation(client, body):
    assert_error(await client.post("/v1/auth/refresh", json=body), 422, "validation_error")


# --------------------------------------------------------------------------- sessions


async def test_logout_revokes_the_session_immediately(client, session_factory, test_user):
    body = (await login(client)).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    response = await client.post("/v1/auth/logout", headers=headers)
    assert response.status_code == 204
    # A different tab may have replaced the shared refresh cookie.
    assert "set-cookie" not in response.headers

    assert_error(await client.get("/v1/me", headers=headers), 401, "invalid_token")
    refresh = await client.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert_error(refresh, 401, "invalid_refresh_token")
    [event] = await audit_events(session_factory, "logout")
    assert event.user_id == test_user.id


async def test_list_sessions(client, session_factory, config, test_user):
    phone = (await login(client, device_name="Phone")).json()
    await login(
        client, headers={**WEB, "User-Agent": "Mozilla/5.0 (Macintosh) Chrome/131.0 Safari/537.36"}
    )
    revoked = await sign_in(session_factory, config, test_user)
    async with session_factory.begin() as session:
        row = await session.get(AuthSession, revoked.session.id)
        row.revoked_at = datetime.now(UTC)

    headers = {"Authorization": f"Bearer {phone['access_token']}"}
    listing = (await client.get("/v1/auth/sessions", headers=headers)).json()
    assert listing["next_cursor"] is None
    [web, mobile] = listing["items"]
    assert (web["current"], web["platform"], web["user_agent"]) == (False, "web", "Chrome on macOS")
    assert (mobile["current"], mobile["device_name"]) == (True, "Phone")
    assert set(mobile) == {
        "id",
        "current",
        "sign_in_method",
        "platform",
        "device_name",
        "user_agent",
        "created_at",
        "last_used_at",
        "expires_at",
    }

    first = (await client.get("/v1/auth/sessions?limit=1", headers=headers)).json()
    assert [item["id"] for item in first["items"]] == [web["id"]]
    rest = await client.get(
        "/v1/auth/sessions", params={"limit": 1, "cursor": first["next_cursor"]}, headers=headers
    )
    assert [item["id"] for item in rest.json()["items"]] == [mobile["id"]]


async def test_revoke_one_session(client, session_factory, config, test_user):
    current = await sign_in(session_factory, config, test_user)
    other = await sign_in(session_factory, config, test_user)
    stranger = await sign_in(
        session_factory, config, await create_user(session_factory, email="s@example.com")
    )

    response = await client.delete(f"/v1/auth/sessions/{other.session.id}", headers=bearer(current))
    assert response.status_code == 204
    assert "set-cookie" not in response.headers
    assert_error(await client.get("/v1/me", headers=bearer(other)), 401, "invalid_token")
    assert (await client.get("/v1/me", headers=bearer(current))).status_code == 200

    for session_id in (
        stranger.session.id,
        other.session.id,
        "00000000-0000-0000-0000-000000000000",
    ):
        response = await client.delete(f"/v1/auth/sessions/{session_id}", headers=bearer(current))
        assert_error(response, 404, "session_not_found")
    assert (await client.get("/v1/me", headers=bearer(stranger))).status_code == 200

    own = await client.delete(f"/v1/auth/sessions/{current.session.id}", headers=bearer(current))
    assert own.status_code == 204
    assert cookies(own)[REFRESH_COOKIE]["max-age"] == "0"
    assert_error(await client.get("/v1/me", headers=bearer(current)), 401, "invalid_token")
    events = await audit_events(session_factory, "session_revoked")
    assert [e.details["revoked_session_id"] for e in events] == [
        str(other.session.id),
        str(current.session.id),
    ]


async def test_revoke_other_sessions(client, session_factory, config, test_user):
    sessions = [await sign_in(session_factory, config, test_user) for _ in range(3)]
    response = await client.post("/v1/auth/sessions/revoke-others", headers=bearer(sessions[0]))
    assert response.json() == {"revoked": 2}
    assert (await client.get("/v1/me", headers=bearer(sessions[0]))).status_code == 200
    for issued in sessions[1:]:
        assert_error(await client.get("/v1/me", headers=bearer(issued)), 401, "invalid_token")


# --------------------------------------------------------------------------- verification


async def register_and_verify_token(client, outbox, email="verify@example.com") -> str:
    await client.post(
        "/v1/auth/register", json={"email": email, "password": NEW_PASSWORD, "name": "V"}
    )
    return token_from(outbox[-1])


async def verify(client, token: str, password: str = NEW_PASSWORD):
    return await client.post("/v1/auth/verify-email", json={"token": token, "password": password})


async def test_verify_email(client, outbox, session_factory):
    token = await register_and_verify_token(client, outbox)
    # The link alone is not enough: it activates only the password chosen at registration.
    wrong = await verify(client, token, "not-the-registration-password")
    assert_error(wrong, 401, "invalid_credentials")
    assert (await verify(client, token)).status_code == 204
    signed_in = await login(client, email="verify@example.com", password=NEW_PASSWORD)
    assert signed_in.json()["user"]["email_verified"] is True
    assert_error(await verify(client, token), 400, "invalid_or_expired_token")
    events = [e.event for e in await audit_events(session_factory)]
    assert events.count("email_verified") == 1
    assert "account_claimed" in events
    assert events.count("login_failed") == 1


async def test_expired_verification_token(client, outbox, session_factory):
    token = await register_and_verify_token(client, outbox)
    async with session_factory.begin() as session:
        await session.execute(
            update(AccountToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert_error(await verify(client, token), 400, "invalid_or_expired_token")


async def test_pending_registrations_keep_independent_links_and_names(
    client, outbox, session_factory
):
    first = await register_and_verify_token(client, outbox)
    payload = {"email": "verify@example.com", "password": NEW_PASSWORD + "-2", "name": "Again"}
    await client.post("/v1/auth/register", json=payload)
    second = token_from(outbox[-1])
    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.email == "verify@example.com"))
        assert user.name == "User"
    assert_error(await verify(client, second, NEW_PASSWORD), 401, "invalid_credentials")
    assert (await verify(client, first, NEW_PASSWORD)).status_code == 204
    assert_error(await verify(client, second, NEW_PASSWORD + "-2"), 400, "invalid_or_expired_token")
    signed_in = await login(client, email="verify@example.com", password=NEW_PASSWORD)
    assert signed_in.json()["user"]["name"] == "V"


async def test_resend_verification(client, outbox, session_factory, test_password_hash):
    # An account from before verification existed: its own password is the one to confirm.
    await create_user(
        session_factory,
        email="legacy@example.com",
        hashed_password=test_password_hash,
        verified=False,
    )
    assert_error(await login(client, email="legacy@example.com"), 401, "invalid_credentials")
    for _ in range(3):
        resent = await client.post(
            "/v1/auth/verify-email/resend", json={"email": "Legacy@example.com"}
        )
        assert resent.status_code == 202
    assert [(e.template, e.to) for e in outbox] == [
        (Template.VERIFY_EMAIL, "legacy@example.com")
    ] * 3
    limited = await client.post(
        "/v1/auth/verify-email/resend", json={"email": "legacy@example.com"}
    )
    assert_error(limited, 429, "rate_limited")
    # Earlier links remain valid until any one claims the account.
    tokens = [token_from(email) for email in outbox]
    assert (await verify(client, tokens[0], TEST_PASSWORD)).status_code == 204
    assert_error(await verify(client, tokens[-1], TEST_PASSWORD), 400, "invalid_or_expired_token")
    assert (await login(client, email="legacy@example.com")).status_code == 200


async def test_resend_does_not_reveal_accounts(client, outbox, session_factory, test_user):
    await create_user(session_factory, email="google-only@example.com", verified=False)
    responses = [
        await client.post("/v1/auth/verify-email/resend", json={"email": email})
        for email in ("test@example.com", "nobody@example.com", "google-only@example.com")
    ]
    assert {r.status_code for r in responses} == {202}
    assert len({r.text for r in responses}) == 1
    assert outbox == []  # Verified, unknown, and no password to confirm.


# --------------------------------------------------------------------------- password reset


async def test_reset_request_does_not_reveal_accounts(client, outbox, session_factory, test_user):
    await create_user(session_factory, email="inactive@example.com", is_active=False)
    responses = [
        await client.post("/v1/auth/password/forgot", json={"email": email})
        for email in ("TEST@example.com", "nobody@example.com", "inactive@example.com")
    ]
    assert {r.status_code for r in responses} == {202}
    assert len({r.text for r in responses}) == 1
    assert [(e.template, e.to) for e in outbox] == [(Template.RESET_PASSWORD, "test@example.com")]
    assert "30 minutes" in outbox[0].text


async def test_password_reset_signs_out_everywhere(
    client, outbox, session_factory, config, test_password_hash
):
    user = await create_user(session_factory, verified=False, hashed_password=test_password_hash)
    sessions = [await sign_in(session_factory, config, user) for _ in range(2)]
    await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    [email] = outbox
    async with session_factory() as session:
        stored = await session.scalar(select(AccountToken))
    lifetime = stored.expires_at - stored.created_at
    assert timedelta(minutes=29) < lifetime <= timedelta(minutes=30, seconds=5)

    token = token_from(email)
    reset = await client.post(
        "/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert reset.status_code == 204
    for issued in sessions:
        assert_error(await client.get("/v1/me", headers=bearer(issued)), 401, "invalid_token")
        refresh = await client.post(
            "/v1/auth/refresh", json={"refresh_token": issued.refresh_token}
        )
        assert_error(refresh, 401, "invalid_refresh_token")
    assert_error(await login(client), 401, "invalid_credentials")
    assert (await login(client, password=NEW_PASSWORD)).status_code == 200
    # The emailed link proved control of the inbox.
    assert (await reload(session_factory, User, user.id)).email_verified_at is not None
    assert outbox[-1].template == Template.PASSWORD_CHANGED
    [event] = await audit_events(session_factory, "password_reset")
    assert event.details == {"sessions_revoked": 2}

    again = await client.post(
        "/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD + "x"}
    )
    assert_error(again, 400, "invalid_or_expired_token")


async def test_password_reset_token_expiry_and_validation(
    client, outbox, session_factory, test_user
):
    await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    token = token_from(outbox[0])
    short = await client.post(
        "/v1/auth/password/reset", json={"token": token, "new_password": "short"}
    )
    assert_error(short, 422, "validation_error")
    async with session_factory.begin() as session:
        await session.execute(
            update(AccountToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    expired = await client.post(
        "/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert_error(expired, 400, "invalid_or_expired_token")


async def test_reset_request_is_rate_limited(client, outbox, test_user):
    for _ in range(3):
        await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    limited = await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    assert_error(limited, 429, "rate_limited")
    assert len(outbox) == 3


# --------------------------------------------------------------------------- re-authentication


async def test_password_reauthentication(client, session_factory, config, test_user):
    stale = datetime.now(UTC) - timedelta(hours=1)
    issued = await sign_in(session_factory, config, test_user, authenticated_at=stale)
    headers = bearer(issued)

    wrong = await client.post("/v1/auth/reauthenticate", json={"password": "nope"}, headers=headers)
    assert_error(wrong, 403, "reauthentication_failed")
    assert (await reload(session_factory, AuthSession, issued.session.id)).authenticated_at == stale

    ok = await client.post(
        "/v1/auth/reauthenticate", json={"password": TEST_PASSWORD}, headers=headers
    )
    assert ok.status_code == 204
    session = await reload(session_factory, AuthSession, issued.session.id)
    assert session.authenticated_at > datetime.now(UTC) - timedelta(minutes=1)
    events = [e.event for e in await audit_events(session_factory)]
    assert events == ["reauthentication_failed", "reauthenticated"]


async def test_reauthentication_backs_off_after_repeated_failures(client, auth_headers):
    for _ in range(5):
        response = await client.post(
            "/v1/auth/reauthenticate", json={"password": "nope"}, headers=auth_headers
        )
        assert_error(response, 403, "reauthentication_failed")
    locked = await client.post(
        "/v1/auth/reauthenticate", json={"password": TEST_PASSWORD}, headers=auth_headers
    )
    assert_error(locked, 429, "rate_limited")


async def test_reauthentication_upgrades_a_legacy_hash(client, session_factory, config):
    legacy = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()
    user = await create_user(session_factory, hashed_password=legacy)
    headers = bearer(await sign_in(session_factory, config, user))
    response = await client.post(
        "/v1/auth/reauthenticate", json={"password": TEST_PASSWORD}, headers=headers
    )
    assert response.status_code == 204
    assert (await reload(session_factory, User, user.id)).hashed_password.startswith("$argon2id$")


@pytest.mark.parametrize("body", [{}, {"password": TEST_PASSWORD, "id_token": "x" * 20}])
async def test_reauthenticate_requires_exactly_one_credential(client, auth_headers, body):
    response = await client.post("/v1/auth/reauthenticate", json=body, headers=auth_headers)
    assert_error(response, 422, "validation_error")


async def test_reset_link_stops_working_if_the_account_is_deactivated(
    client, outbox, session_factory, test_user
):
    await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    async with session_factory.begin() as session:
        await session.execute(update(User).values(is_active=False))
    response = await client.post(
        "/v1/auth/password/reset",
        json={"token": token_from(outbox[0]), "new_password": NEW_PASSWORD},
    )
    assert_error(response, 400, "invalid_or_expired_token")


# --------------------------------------------------------------------------- races and timing


@pytest.mark.parametrize("legacy", [False, True])
async def test_sign_in_racing_a_password_reset_keeps_no_session(
    client, outbox, session_factory, test_user, monkeypatch, legacy
):
    """A sign-in that checked the old password must not survive a reset (B3)."""
    from app.modules.auth import service as service_module

    if legacy:
        async with session_factory.begin() as db:
            user = await db.get(User, test_user.id)
            user.hashed_password = bcrypt.hashpw(
                TEST_PASSWORD.encode(), bcrypt.gensalt(rounds=4)
            ).decode()
    await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    reset_token = token_from(outbox[-1])
    checked, release = asyncio.Event(), asyncio.Event()
    verify = service_module.verify_password

    async def pause_after_check(password, hashed):
        result = await verify(password, hashed)
        if password == TEST_PASSWORD:
            checked.set()
            await release.wait()
        return result

    monkeypatch.setattr(service_module, "verify_password", pause_after_check)
    async with asyncio.timeout(10):
        signing_in = asyncio.create_task(login(client))
        await checked.wait()
        reset = await client.post(
            "/v1/auth/password/reset", json={"token": reset_token, "new_password": NEW_PASSWORD}
        )
        assert reset.status_code == 204
        release.set()
        assert_error(await signing_in, 401, "invalid_credentials")
    async with session_factory() as session:
        assert await session.scalar(select(AuthSession)) is None
        hashed = (await session.get(User, test_user.id)).hashed_password
    assert (await verify(NEW_PASSWORD, hashed))[0]


async def test_concurrent_reset_links_are_serialized(client, outbox, test_user, monkeypatch):
    """Hold the first token lock while a second redemption waits on the user."""
    from app.modules.auth.repository import AccountTokenRepository

    for _ in range(2):
        await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    tokens = [token_from(email) for email in outbox]
    locked, release = asyncio.Event(), asyncio.Event()
    original = AccountTokenRepository.lock_valid
    first = True

    async def pause(self, purpose, digest):
        nonlocal first
        result = await original(self, purpose, digest)
        if first:
            first = False
            locked.set()
            await release.wait()
        return result

    monkeypatch.setattr(AccountTokenRepository, "lock_valid", pause)
    async with asyncio.timeout(10):
        one = asyncio.create_task(
            client.post(
                "/v1/auth/password/reset", json={"token": tokens[0], "new_password": NEW_PASSWORD}
            )
        )
        await locked.wait()
        two = asyncio.create_task(
            client.post(
                "/v1/auth/password/reset", json={"token": tokens[1], "new_password": NEW_PASSWORD}
            )
        )
        await asyncio.sleep(0.1)
        assert not two.done()
        release.set()
        responses = await asyncio.gather(one, two)
    assert sorted(response.status_code for response in responses) == [204, 400]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/auth/password/forgot", {}),
        ("/v1/auth/register", {"password": NEW_PASSWORD, "name": "Someone"}),
        ("/v1/auth/verify-email/resend", {}),
    ],
)
async def test_account_lookups_happen_after_the_response(
    app, session_factory, test_db_engine, test_password_hash, path, body
):
    """Responses must not depend on whether an account exists, timing included (M10)."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import event

    await create_user(
        session_factory,
        email="known@example.com",
        hashed_password=test_password_hash,
        verified=False,
    )
    responded: list[bool] = []
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if not responded:
            statements.append(" ".join(statement.split()))

    async def watched(scope, receive, send):
        async def mark(message):
            if message["type"] == "http.response.start":
                responded.append(True)
            await send(message)

        await app(scope, receive, mark)

    event.listen(test_db_engine.sync_engine, "before_cursor_execute", record)
    before_response = []
    async with AsyncClient(transport=ASGITransport(app=watched), base_url="http://localhost") as c:
        for email in ("known@example.com", "unknown@example.com"):
            responded.clear()
            statements.clear()
            response = await c.post(path, json={**body, "email": email})
            assert response.status_code == 202
            before_response.append(list(statements))
    event.remove(test_db_engine.sync_engine, "before_cursor_execute", record)
    assert before_response[0] == before_response[1] == []


async def test_pending_verification_links_are_bounded(client, outbox, session_factory, monkeypatch):
    from app.modules.auth import limits

    monkeypatch.setattr(
        limits, "REGISTER_PER_ACCOUNT", Rule("test_pending", 10, timedelta(hours=1))
    )
    for index in range(6):
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": "bounded@example.com",
                "name": f"Owner {index}",
                "password": NEW_PASSWORD,
            },
        )
        assert response.status_code == 202
    tokens = [token_from(email) for email in outbox]
    async with session_factory() as db:
        assert len((await db.scalars(select(AccountToken))).all()) == 5
    assert_error(await verify(client, tokens[0]), 400, "invalid_or_expired_token")
    assert (await verify(client, tokens[1])).status_code == 204
    assert (await login(client, email="bounded@example.com", password=NEW_PASSWORD)).json()["user"][
        "name"
    ] == "Owner 1"
