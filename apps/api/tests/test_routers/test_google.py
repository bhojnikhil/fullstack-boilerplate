"""Sign in with Google (ID tokens), linking rules, link/unlink and Google re-authentication."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.audit import AuditEvent
from app.integrations.google_id_token import GoogleUnavailableError
from app.modules.auth.models import AuthSession, OAuthAccount, User
from tests.conftest import WEB_ORIGIN, bearer, create_user, sign_in
from tests.test_http_contract import assert_error
from tests.test_routers.test_auth import MOBILE, WEB, cookies, login

STALE = datetime.now(UTC) - timedelta(hours=1)


async def google_sign_in(client, token: str, headers=MOBILE, **body):
    return await client.post("/v1/auth/google", json={"id_token": token, **body}, headers=headers)


async def linked_accounts(session_factory) -> list[OAuthAccount]:
    async with session_factory() as session:
        return list(await session.scalars(select(OAuthAccount)))


async def events(session_factory) -> list[str]:
    async with session_factory() as session:
        rows = await session.scalars(select(AuditEvent).order_by(AuditEvent.created_at))
        return [row.event for row in rows]


async def test_new_google_user_is_created_verified_and_linked(client, google, session_factory):
    response = await google_sign_in(
        client, google.issue(email="New.Person@Gmail.com"), device_name="iPhone"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["refresh_token"]
    assert body["user"]["email"] == "new.person@gmail.com"
    assert body["user"]["email_verified"] is True
    assert body["user"]["name"] == "Google User"
    assert body["user"]["avatar_url"] == "https://example.com/avatar.png"
    assert body["user"]["sign_in_methods"] == ["google"]

    [account] = await linked_accounts(session_factory)
    assert account.provider_account_id == "google-subject-1"
    assert set(OAuthAccount.__table__.columns.keys()) == {
        "id",
        "user_id",
        "provider",
        "provider_account_id",
        "created_at",
        "updated_at",
    }
    async with session_factory() as session:
        auth_session = await session.scalar(select(AuthSession))
    assert (auth_session.sign_in_method, auth_session.device_name) == ("google", "iPhone")
    assert await events(session_factory) == [
        "account_registered",
        "google_linked",
        "login_succeeded",
    ]

    again = await google_sign_in(client, google.issue(email="new.person@gmail.com"))
    assert again.json()["user"]["id"] == body["user"]["id"]
    assert len(await linked_accounts(session_factory)) == 1


async def test_web_google_sign_in_uses_cookies_and_checks_origin(client, google):
    response = await google_sign_in(client, google.issue(), headers=WEB)
    assert response.status_code == 200
    assert response.json()["refresh_token"] is None
    assert response.json()["csrf_token"]
    assert "refresh_token" in cookies(response)

    cross_site = {"X-Platform": "web", "Origin": "https://evil.example"}
    assert_error(
        await google_sign_in(client, google.issue(), headers=cross_site), 403, "csrf_failed"
    )
    no_origin = {"X-Platform": "web"}
    assert_error(
        await google_sign_in(client, google.issue(), headers=no_origin), 403, "csrf_failed"
    )
    assert WEB["Origin"] == WEB_ORIGIN


async def test_verified_local_account_is_linked_automatically(
    client, google, session_factory, test_user
):
    response = await google_sign_in(client, google.issue(email="test@example.com"))
    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(test_user.id)
    assert response.json()["user"]["sign_in_methods"] == ["password", "google"]
    [account] = await linked_accounts(session_factory)
    assert account.user_id == test_user.id
    async with session_factory() as session:
        [event] = await session.scalars(
            select(AuditEvent).where(AuditEvent.event == "google_linked")
        )
    assert event.details == {"automatic": True}


async def test_unverified_local_account_requires_explicit_linking(
    client, google, session_factory, test_password_hash
):
    owner = await create_user(
        session_factory,
        email="victim@example.com",
        hashed_password=test_password_hash,
        verified=False,
    )
    response = await google_sign_in(client, google.issue(email="victim@example.com"))
    error = assert_error(response, 409, "google_link_required")
    assert "Sign in" in error["message"]
    assert await linked_accounts(session_factory) == []
    async with session_factory() as session:
        assert await session.scalar(select(AuthSession)) is None
        assert (await session.get(User, owner.id)).email_verified_at is None
    assert await events(session_factory) == ["login_failed"]


async def test_unverified_google_email_never_creates_or_links(
    client, google, session_factory, test_user
):
    for email in ("someone.new@example.com", "test@example.com"):
        token = google.issue(email=email, email_verified=False)
        assert_error(await google_sign_in(client, token), 403, "google_email_unverified")
    assert await linked_accounts(session_factory) == []
    async with session_factory() as session:
        assert len(list(await session.scalars(select(User)))) == 1


async def test_existing_link_signs_in_even_if_google_email_changed(
    client, google, session_factory, test_user
):
    async with session_factory.begin() as session:
        session.add(
            OAuthAccount(user_id=test_user.id, provider="google", provider_account_id="sub-9")
        )
    token = google.issue(subject="sub-9", email="renamed@gmail.com", email_verified=False)
    response = await google_sign_in(client, token)
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "test@example.com"


async def test_google_sign_in_marks_matching_unverified_email_verified(
    client, google, session_factory
):
    user = await create_user(session_factory, email="later@example.com", verified=False)
    async with session_factory.begin() as session:
        session.add(OAuthAccount(user_id=user.id, provider="google", provider_account_id="sub-7"))
    response = await google_sign_in(
        client, google.issue(subject="sub-7", email="later@example.com")
    )
    assert response.json()["user"]["email_verified"] is True


async def test_inactive_google_user_cannot_sign_in(client, google, session_factory, test_user):
    async with session_factory.begin() as session:
        await session.execute(update(User).values(is_active=False))
    response = await google_sign_in(client, google.issue(email="test@example.com"))
    assert_error(response, 403, "inactive_user")


async def test_google_errors(client, app, google, config):
    assert_error(await google_sign_in(client, "unknown-token-value"), 401, "invalid_google_token")
    down = google.fail(GoogleUnavailableError())
    assert_error(await google_sign_in(client, down), 503, "google_unavailable")

    app.state.google_verifier = None
    assert_error(await google_sign_in(client, google.issue()), 404, "google_sign_in_disabled")
    app.state.google_verifier = google
    config.google_auth_enabled = False
    assert_error(await google_sign_in(client, google.issue()), 404, "google_sign_in_disabled")


async def test_google_sign_in_is_rate_limited(client, app, google):
    from app.core.ratelimit import Rule

    app.state.rate_limiter.overrides["google_account"] = Rule(
        "google_account", 1, timedelta(minutes=15)
    )
    assert (await google_sign_in(client, google.issue())).status_code == 200
    assert_error(await google_sign_in(client, google.issue()), 429, "rate_limited")


# --------------------------------------------------------------------------- explicit linking


async def test_explicit_link_after_signing_in(
    client, google, session_factory, config, test_password_hash
):
    owner = await create_user(
        session_factory,
        email="owner@example.com",
        hashed_password=test_password_hash,
        verified=False,
    )
    signed_in = await login(client, email="owner@example.com")
    headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
    token = google.issue(subject="owner-sub", email="owner@example.com")

    linked = await client.post("/v1/auth/google/link", json={"id_token": token}, headers=headers)
    assert linked.status_code == 204
    [account] = await linked_accounts(session_factory)
    assert (account.user_id, account.provider_account_id) == (owner.id, "owner-sub")
    profile = (await client.get("/v1/me", headers=headers)).json()
    assert profile["sign_in_methods"] == ["password", "google"]
    assert profile["email_verified"] is True  # Google verified the same address.
    # Linking the same identity again is a no-op.
    again = await client.post("/v1/auth/google/link", json={"id_token": token}, headers=headers)
    assert again.status_code == 204
    # Now Google sign-in works for this account.
    response = await google_sign_in(client, google.issue(subject="owner-sub", email="x@gmail.com"))
    assert response.json()["user"]["id"] == str(owner.id)


async def test_link_requires_recent_authentication(
    client, google, session_factory, config, test_user
):
    issued = await sign_in(session_factory, config, test_user, authenticated_at=STALE)
    response = await client.post(
        "/v1/auth/google/link", json={"id_token": google.issue()}, headers=bearer(issued)
    )
    assert_error(response, 403, "reauthentication_required")
    assert await linked_accounts(session_factory) == []


async def test_link_conflicts(client, google, session_factory, config, test_user, auth_headers):
    other = await create_user(session_factory, email="other@example.com")
    async with session_factory.begin() as session:
        session.add(OAuthAccount(user_id=other.id, provider="google", provider_account_id="taken"))

    in_use = await client.post(
        "/v1/auth/google/link",
        json={"id_token": google.issue(subject="taken")},
        headers=auth_headers,
    )
    assert_error(in_use, 409, "google_account_in_use")

    first = google.issue(subject="first")
    assert (
        await client.post("/v1/auth/google/link", json={"id_token": first}, headers=auth_headers)
    ).status_code == 204
    second = await client.post(
        "/v1/auth/google/link",
        json={"id_token": google.issue(subject="second")},
        headers=auth_headers,
    )
    assert_error(second, 409, "google_already_linked")

    # Automatic linking hits the same rule.
    auto = await google_sign_in(client, google.issue(subject="third", email="test@example.com"))
    assert_error(auto, 409, "google_already_linked")


async def test_unlink(client, google, session_factory, test_user, auth_headers):
    assert_error(
        await client.delete("/v1/auth/google/link", headers=auth_headers), 404, "google_not_linked"
    )
    await client.post(
        "/v1/auth/google/link", json={"id_token": google.issue()}, headers=auth_headers
    )
    response = await client.delete("/v1/auth/google/link", headers=auth_headers)
    assert response.status_code == 204
    assert await linked_accounts(session_factory) == []
    assert "google_unlinked" in await events(session_factory)


async def test_unlink_keeps_at_least_one_sign_in_method(client, google, session_factory):
    signed_in = await google_sign_in(client, google.issue(email="only-google@example.com"))
    headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
    response = await client.delete("/v1/auth/google/link", headers=headers)
    assert_error(response, 409, "last_sign_in_method")
    assert len(await linked_accounts(session_factory)) == 1


async def test_unlink_requires_recent_authentication(
    client, google, session_factory, config, test_user
):
    async with session_factory.begin() as session:
        session.add(OAuthAccount(user_id=test_user.id, provider="google", provider_account_id="s"))
    issued = await sign_in(session_factory, config, test_user, authenticated_at=STALE)
    response = await client.delete("/v1/auth/google/link", headers=bearer(issued))
    assert_error(response, 403, "reauthentication_required")


# --------------------------------------------------------------------------- re-authentication


@pytest.mark.parametrize(
    ("subject", "issued_ago", "expected"),
    [
        ("mine", timedelta(minutes=1), 204),
        ("mine", timedelta(minutes=11), 403),  # Not fresh: issued before the re-auth window.
        ("someone-else", timedelta(minutes=1), 403),
        (None, None, 403),  # Invalid token.
    ],
)
async def test_google_reauthentication(
    client, google, session_factory, config, test_user, subject, issued_ago, expected
):
    async with session_factory.begin() as session:
        session.add(
            OAuthAccount(user_id=test_user.id, provider="google", provider_account_id="mine")
        )
    issued = await sign_in(session_factory, config, test_user, authenticated_at=STALE)
    token = (
        google.issue(subject=subject, issued_at=datetime.now(UTC) - issued_ago)
        if subject
        else "not-a-google-token"
    )
    response = await client.post(
        "/v1/auth/reauthenticate", json={"id_token": token}, headers=bearer(issued)
    )
    if expected == 204:
        assert response.status_code == 204
        async with session_factory() as session:
            refreshed = await session.get(AuthSession, issued.session.id)
        assert refreshed.authenticated_at > STALE
    else:
        assert_error(response, 403, "reauthentication_failed")


async def test_google_reauthentication_when_google_is_down(client, google, auth_headers):
    token = google.fail(GoogleUnavailableError())
    response = await client.post(
        "/v1/auth/reauthenticate", json={"id_token": token}, headers=auth_headers
    )
    assert_error(response, 503, "google_unavailable")


async def test_concurrent_registration_falls_back_to_the_linking_rules(
    client, google, session_factory, monkeypatch
):
    """Another request created the user between our lookup and insert."""
    from app.modules.auth.repository import UserRepository

    await create_user(session_factory, email="racer@example.com")
    lookup = UserRepository.get_by_email
    calls = []

    async def first_lookup_misses(self, email):
        calls.append(email)
        return None if len(calls) == 1 else await lookup(self, email)

    monkeypatch.setattr(UserRepository, "get_by_email", first_lookup_misses)
    response = await google_sign_in(client, google.issue(email="racer@example.com"))
    assert response.status_code == 200  # The existing account is verified: linked.
    assert len(calls) == 2
    assert len(await linked_accounts(session_factory)) == 1


async def test_concurrent_link_of_the_same_identity_is_not_an_error(
    client, google, session_factory, test_user, monkeypatch
):
    """Another request linked this Google identity to this user first."""
    from app.modules.auth.repository import OAuthAccountRepository

    async with session_factory.begin() as session:
        session.add(
            OAuthAccount(user_id=test_user.id, provider="google", provider_account_id="sub-race")
        )
    lookup = OAuthAccountRepository.get
    calls = []

    async def first_lookup_misses(self, provider, subject):
        calls.append(subject)
        return None if len(calls) == 1 else await lookup(self, provider, subject)

    monkeypatch.setattr(OAuthAccountRepository, "get", first_lookup_misses)
    token = google.issue(subject="sub-race", email="test@example.com")
    response = await google_sign_in(client, token)
    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(test_user.id)
    assert len(await linked_accounts(session_factory)) == 1
