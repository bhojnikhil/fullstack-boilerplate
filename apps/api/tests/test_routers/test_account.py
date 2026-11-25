"""The signed-in user's account: /v1/me."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text

from app.core.audit import AuditEvent
from app.integrations.email.templates import Template
from app.modules.auth.deletion import AccountDeletionBlockedError
from app.modules.auth.models import AccountToken, AuthSession, OAuthAccount, User
from app.modules.items.models import Item
from tests.conftest import TEST_PASSWORD, bearer, create_user, sign_in
from tests.test_http_contract import assert_error
from tests.test_routers.test_auth import NEW_PASSWORD, cookies, login, token_from

STALE = datetime.now(UTC) - timedelta(hours=1)


async def count(session_factory, model) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def test_get_and_update_profile(client, auth_headers, test_user):
    profile = await client.get("/v1/me", headers=auth_headers)
    assert profile.status_code == 200
    assert profile.json() == {
        **profile.json(),
        "id": str(test_user.id),
        "email": "test@example.com",
        "email_verified": True,
        "name": "Test User",
        "sign_in_methods": ["password"],
    }
    updated = await client.patch("/v1/me", json={"name": "  Renamed  "}, headers=auth_headers)
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["updated_at"] >= profile.json()["updated_at"]
    unchanged = await client.patch("/v1/me", json={}, headers=auth_headers)
    assert unchanged.json()["name"] == "Renamed"
    assert_error(await client.get("/v1/me"), 401, "unauthorized")


# --------------------------------------------------------------------------- password


async def test_change_password_signs_out_other_sessions(
    client, outbox, session_factory, config, test_user
):
    current = await sign_in(session_factory, config, test_user)
    other = await sign_in(session_factory, config, test_user)
    response = await client.post(
        "/v1/me/password",
        json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD},
        headers=bearer(current),
    )
    assert response.status_code == 204
    assert (await client.get("/v1/me", headers=bearer(current))).status_code == 200
    assert_error(await client.get("/v1/me", headers=bearer(other)), 401, "invalid_token")
    assert_error(await login(client), 401, "invalid_credentials")
    assert (await login(client, password=NEW_PASSWORD)).status_code == 200
    assert [e.template for e in outbox] == [Template.PASSWORD_CHANGED]
    async with session_factory() as session:
        [event] = await session.scalars(
            select(AuditEvent).where(AuditEvent.event == "password_changed")
        )
    assert event.details == {"sessions_revoked": 1}


async def test_change_password_rejects_wrong_current_password(
    client, outbox, session_factory, auth_headers
):
    response = await client.post(
        "/v1/me/password",
        json={"current_password": "wrong", "new_password": NEW_PASSWORD},
        headers=auth_headers,
    )
    assert_error(response, 403, "reauthentication_failed")
    assert (await login(client)).status_code == 200
    assert outbox == []
    async with session_factory() as session:
        [event] = await session.scalars(
            select(AuditEvent).where(AuditEvent.event == "reauthentication_failed")
        )
    assert event.details == {"method": "password", "purpose": "change_password"}


async def test_change_password_requires_an_existing_password(client, session_factory, config):
    user = await create_user(session_factory, email="google-only@example.com")
    response = await client.post(
        "/v1/me/password",
        json={"current_password": "anything", "new_password": NEW_PASSWORD},
        headers=bearer(await sign_in(session_factory, config, user)),
    )
    assert_error(response, 409, "password_not_set")


async def test_change_password_validates_new_password(client, auth_headers):
    response = await client.post(
        "/v1/me/password",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
        headers=auth_headers,
    )
    assert_error(response, 422, "validation_error")


# --------------------------------------------------------------------------- email


async def test_change_email_after_confirming_the_new_address(
    client, outbox, session_factory, auth_headers, test_user
):
    response = await client.post(
        "/v1/me/email", json={"new_email": "New@Example.com"}, headers=auth_headers
    )
    assert response.status_code == 202
    [confirmation] = outbox
    assert (confirmation.template, confirmation.to) == (Template.EMAIL_CHANGE, "new@example.com")
    # Nothing changes until the new address is confirmed.
    assert (await client.get("/v1/me", headers=auth_headers)).json()["email"] == "test@example.com"

    confirmed = await client.post(
        "/v1/auth/email/confirm", json={"token": token_from(confirmation)}
    )
    assert confirmed.status_code == 204
    profile = (await client.get("/v1/me", headers=auth_headers)).json()
    assert (profile["email"], profile["email_verified"]) == ("new@example.com", True)
    assert (outbox[-1].template, outbox[-1].to) == (Template.EMAIL_CHANGED, "test@example.com")
    assert (await login(client, email="new@example.com")).status_code == 200
    assert_error(await login(client), 401, "invalid_credentials")

    reused = await client.post("/v1/auth/email/confirm", json={"token": token_from(confirmation)})
    assert_error(reused, 400, "invalid_or_expired_token")


async def test_links_sent_to_the_previous_address_stop_working(
    client, outbox, session_factory, auth_headers, test_user
):
    await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    reset_token = token_from(outbox[-1])
    await client.post("/v1/me/email", json={"new_email": "moved@example.com"}, headers=auth_headers)
    await client.post("/v1/auth/email/confirm", json={"token": token_from(outbox[-1])})

    response = await client.post(
        "/v1/auth/password/reset", json={"token": reset_token, "new_password": NEW_PASSWORD}
    )
    assert_error(response, 400, "invalid_or_expired_token")


async def test_verification_link_for_an_old_address_is_rejected(client, outbox, session_factory):
    await client.post(
        "/v1/auth/register",
        json={"email": "first@example.com", "password": NEW_PASSWORD, "name": "First"},
    )
    stale_link = token_from(outbox[-1])
    # Point the account at a different address, as if its email changed meanwhile.
    async with session_factory.begin() as session:
        await session.execute(text("UPDATE users SET email = 'second@example.com'"))
    response = await client.post(
        "/v1/auth/verify-email", json={"token": stale_link, "password": NEW_PASSWORD}
    )
    assert_error(response, 400, "invalid_or_expired_token")


async def test_change_email_does_not_reveal_taken_addresses(
    client, outbox, session_factory, auth_headers
):
    await create_user(session_factory, email="taken@example.com")
    for new_email in ("taken@example.com", "TEST@example.com"):
        response = await client.post(
            "/v1/me/email", json={"new_email": new_email}, headers=auth_headers
        )
        assert response.status_code == 202
    assert outbox == []


async def test_change_email_confirmation_fails_if_the_address_was_taken_since(
    client, outbox, session_factory, auth_headers
):
    await client.post("/v1/me/email", json={"new_email": "race@example.com"}, headers=auth_headers)
    await create_user(session_factory, email="Race@Example.com")
    response = await client.post("/v1/auth/email/confirm", json={"token": token_from(outbox[0])})
    assert_error(response, 409, "email_in_use")


async def test_email_change_racing_a_registration_raises_no_database_error(
    client, outbox, session_factory, auth_headers, test_db_engine
):
    """A unique violation would put the address in Postgres's error log."""
    from sqlalchemy import event

    from app.modules.auth.repository import UserRepository

    await client.post("/v1/me/email", json={"new_email": "race@example.com"}, headers=auth_headers)
    database_errors: list[str] = []
    event.listen(
        test_db_engine.sync_engine,
        "handle_error",
        lambda context: database_errors.append(type(context.original_exception).__name__),
    )
    async with session_factory() as registration, registration.begin():
        # A registration for the same address, not yet committed.
        await UserRepository(registration).create("Race@example.com", "Racer")
        confirm = asyncio.create_task(
            client.post("/v1/auth/email/confirm", json={"token": token_from(outbox[0])})
        )
        await asyncio.sleep(0.3)  # The confirmation waits on the address's lock.
        assert not confirm.done()
    response = await confirm
    assert_error(response, 409, "email_in_use")
    assert database_errors == []
    assert (await client.get("/v1/me", headers=auth_headers)).json()["email"] == "test@example.com"


async def test_change_email_confirmation_for_an_inactive_account(
    client, outbox, session_factory, auth_headers
):
    await client.post("/v1/me/email", json={"new_email": "new@example.com"}, headers=auth_headers)
    async with session_factory.begin() as session:
        await session.execute(text("UPDATE users SET is_active = false"))
    response = await client.post("/v1/auth/email/confirm", json={"token": token_from(outbox[0])})
    assert_error(response, 400, "invalid_or_expired_token")


async def test_change_email_requires_recent_authentication(
    client, outbox, session_factory, config, test_user
):
    issued = await sign_in(session_factory, config, test_user, authenticated_at=STALE)
    response = await client.post(
        "/v1/me/email", json={"new_email": "new@example.com"}, headers=bearer(issued)
    )
    assert_error(response, 403, "reauthentication_required")
    assert outbox == []


# --------------------------------------------------------------------------- deletion


async def test_delete_account_requires_recent_authentication(
    client, session_factory, config, test_user
):
    issued = await sign_in(session_factory, config, test_user, authenticated_at=STALE)
    assert_error(
        await client.delete("/v1/me", headers=bearer(issued)), 403, "reauthentication_required"
    )
    assert await count(session_factory, User) == 1

    reauth = await client.post(
        "/v1/auth/reauthenticate", json={"password": TEST_PASSWORD}, headers=bearer(issued)
    )
    assert reauth.status_code == 204
    assert (await client.delete("/v1/me", headers=bearer(issued))).status_code == 204
    assert await count(session_factory, User) == 0


async def test_delete_account_removes_personal_data(
    client, outbox, session_factory, config, test_user, google
):
    issued = await sign_in(session_factory, config, test_user)
    other_device = await sign_in(session_factory, config, test_user)
    headers = bearer(issued)
    await client.post(
        "/v1/items", json={"title": "mine"}, headers={**headers, "Idempotency-Key": "k"}
    )
    await client.post("/v1/auth/google/link", json={"id_token": google.issue()}, headers=headers)
    await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    survivor = await create_user(session_factory, email="survivor@example.com")

    response = await client.delete("/v1/me", headers=headers)
    assert response.status_code == 204
    assert cookies(response)["refresh_token"]["max-age"] == "0"

    for model in (AuthSession, OAuthAccount, AccountToken, Item):
        assert await count(session_factory, model) == 0, model
    async with session_factory() as session:
        assert [user.id for user in await session.scalars(select(User))] == [survivor.id]
        assert await session.scalar(text("SELECT count(*) FROM idempotency_records")) == 0
        assert await session.scalar(text("SELECT count(*) FROM refresh_tokens")) == 0
        deleted = await session.scalar(
            select(AuditEvent).where(AuditEvent.event == "account_deleted")
        )
    # The audit trail keeps a pseudonymous record (no email or name).
    assert deleted.user_id == test_user.id
    assert "test@example.com" not in str(deleted.details)
    for issued_tokens in (issued, other_device):
        assert_error(
            await client.get("/v1/me", headers=bearer(issued_tokens)), 401, "invalid_token"
        )
    assert (outbox[-1].template, outbox[-1].to) == (Template.ACCOUNT_DELETED, "test@example.com")


class RecordingHook:
    def __init__(self, block: bool = False) -> None:
        self.block = block
        self.calls: list[str] = []

    async def check(self, db, user) -> None:
        self.calls.append("check")
        if self.block:
            raise AccountDeletionBlockedError(
                "Transfer ownership of your workspaces first.", {"workspaces": ["w1"]}
            )

    async def before_delete(self, db, user) -> None:
        self.calls.append("before_delete")
        await db.execute(text("SELECT 1"))


async def test_deletion_hooks_can_block_or_clean_up(
    app, client, outbox, session_factory, auth_headers
):
    blocking = RecordingHook(block=True)
    app.state.account_deletion_hooks.append(blocking)
    response = await client.delete("/v1/me", headers=auth_headers)
    error = assert_error(response, 409, "account_deletion_blocked")
    assert error["message"] == "Transfer ownership of your workspaces first."
    assert error["details"] == {"workspaces": ["w1"]}
    assert blocking.calls == ["check"]
    assert await count(session_factory, User) == 1
    assert outbox == []

    app.state.account_deletion_hooks[:] = [cleanup := RecordingHook()]
    assert (await client.delete("/v1/me", headers=auth_headers)).status_code == 204
    assert cleanup.calls == ["check", "before_delete"]
    assert await count(session_factory, User) == 0


async def test_unverified_accounts_cannot_start_an_email_change(
    client, outbox, session_factory, config
):
    user = await create_user(session_factory, email="unproven@example.com", verified=False)
    headers = bearer(await sign_in(session_factory, config, user))
    response = await client.post(
        "/v1/me/email", json={"new_email": "elsewhere@example.com"}, headers=headers
    )
    assert_error(response, 403, "email_verification_required")
    assert outbox == []


async def test_password_reset_cancels_pending_email_changes(
    client, outbox, session_factory, auth_headers
):
    """Whoever had a session (maybe not the owner) cannot finish an email change after
    the owner resets the password (B2)."""
    await client.post(
        "/v1/me/email", json={"new_email": "attacker@example.com"}, headers=auth_headers
    )
    change_link = token_from(outbox[-1])
    await client.post("/v1/auth/password/forgot", json={"email": "test@example.com"})
    reset = await client.post(
        "/v1/auth/password/reset",
        json={"token": token_from(outbox[-1]), "new_password": NEW_PASSWORD},
    )
    assert reset.status_code == 204
    late = await client.post("/v1/auth/email/confirm", json={"token": change_link})
    assert_error(late, 400, "invalid_or_expired_token")
    assert_error(await client.get("/v1/me", headers=auth_headers), 401, "invalid_token")


async def test_reset_of_an_unverified_account_removes_unproven_identities(
    client, outbox, session_factory, config, test_password_hash
):
    """Identities linked before anyone proved the inbox go when the owner resets (B2)."""
    user = await create_user(
        session_factory,
        email="legacy@example.com",
        hashed_password=test_password_hash,
        verified=False,
    )
    squatter_session = await sign_in(session_factory, config, user)
    async with session_factory.begin() as session:
        session.add(
            OAuthAccount(
                user_id=user.id,
                provider="google",
                provider_account_id="legacy-google",
                state="unconfirmed",
            )
        )
    await client.post("/v1/auth/password/forgot", json={"email": "legacy@example.com"})
    reset = await client.post(
        "/v1/auth/password/reset",
        json={"token": token_from(outbox[-1]), "new_password": NEW_PASSWORD},
    )
    assert reset.status_code == 204
    assert await count(session_factory, OAuthAccount) == 0
    assert_error(await client.get("/v1/me", headers=bearer(squatter_session)), 401, "invalid_token")
    signed_in = await login(client, email="legacy@example.com", password=NEW_PASSWORD)
    assert signed_in.json()["user"]["sign_in_methods"] == ["password"]


async def test_email_change_and_reauthentication_are_rate_limited_per_ip(app, client, auth_headers):
    from app.core.ratelimit import Rule

    limiter = app.state.rate_limiter
    limiter.overrides["email_change_ip"] = Rule("email_change_ip", 1, timedelta(hours=1))
    limiter.overrides["reauth_ip"] = Rule("reauth_ip", 1, timedelta(minutes=15))
    body = {"new_email": "first@example.com"}
    assert (await client.post("/v1/me/email", json=body, headers=auth_headers)).status_code == 202
    assert_error(
        await client.post("/v1/me/email", json=body, headers=auth_headers), 429, "rate_limited"
    )
    reauth = {"password": TEST_PASSWORD}
    first = await client.post("/v1/auth/reauthenticate", json=reauth, headers=auth_headers)
    assert first.status_code == 204
    assert_error(
        await client.post("/v1/auth/reauthenticate", json=reauth, headers=auth_headers),
        429,
        "rate_limited",
    )
