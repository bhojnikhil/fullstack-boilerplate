"""Invitations: link and email flavors, single use, expiry, revocation and accept rules."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import create_workspace, owner_query, person
from tests.test_http_contract import assert_error


@pytest.fixture
def path(workspace):
    return f"/v1/workspaces/{workspace.id}/invitations"


async def accept(client, headers, token):
    return await client.post("/v1/invitations/accept", headers=headers, json={"token": token})


async def make_link(client, auth_headers, path, **body):
    response = await client.post(path, headers=auth_headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def expire(owner_sessions, invitation_id):
    async with owner_sessions.begin() as db:
        await db.execute(
            text("UPDATE invitations SET expires_at = :t WHERE id = :i"),
            {"t": datetime.now(UTC) - timedelta(seconds=1), "i": invitation_id},
        )


async def test_link_invitation_is_hashed_single_use_and_joins_the_workspace(
    client, auth_headers, path, session_factory, config, owner_engine, workspace
):
    invite = await make_link(client, auth_headers, path)
    token = invite["token"]
    assert invite["email"] is None and invite["status"] == "pending"
    assert invite["link"] == f"http://localhost:3000/invite#token={token}"

    stored = await owner_query(owner_engine, "SELECT token_hash FROM invitations")
    assert stored == [(hashlib.sha256(token.encode()).hexdigest(),)]
    listed = (await client.get(path, headers=auth_headers)).json()["items"]
    assert "token" not in listed[0] and token not in str(listed)

    _, joiner = await person(session_factory, config, "joiner@example.com")
    joined = await accept(client, joiner, token)
    assert joined.status_code == 200
    assert joined.json()["id"] == str(workspace.id) and joined.json()["role"] == "member"
    # Single use: a second person (or the same one again) is turned away.
    _, other = await person(session_factory, config, "other@example.com")
    assert_error(await accept(client, other, token), 404, "invalid_invitation")
    assert_error(await accept(client, joiner, token), 404, "invalid_invitation")
    assert (await client.get(path, headers=auth_headers)).json()["items"][0]["status"] == "accepted"


async def test_concurrent_accepts_admit_exactly_one(
    client, auth_headers, path, session_factory, config
):
    token = (await make_link(client, auth_headers, path))["token"]
    people = [await person(session_factory, config, f"p{i}@example.com") for i in range(4)]
    results = await asyncio.gather(*(accept(client, headers, token) for _, headers in people))
    assert sorted(r.status_code for r in results) == [200, 404, 404, 404]


async def test_expired_revoked_unknown_and_malformed_tokens_look_identical(
    client, auth_headers, path, session_factory, config, owner_sessions
):
    _, joiner = await person(session_factory, config, "joiner@example.com")
    expired = await make_link(client, auth_headers, path)
    await expire(owner_sessions, expired["id"])
    revoked = await make_link(client, auth_headers, path)
    assert (await client.delete(f"{path}/{revoked['id']}", headers=auth_headers)).status_code == 204
    bodies = []
    for token in (expired["token"], revoked["token"], "x" * 43, "short" * 5):
        response = await accept(client, joiner, token)
        assert_error(response, 404, "invalid_invitation")
        bodies.append(response.json())
    assert all(body == bodies[0] for body in bodies)
    assert (await client.get(path, headers=auth_headers)).json()["items"][1]["status"] == "expired"


async def test_email_invitation_is_mailed_and_bound_to_the_address(
    client, auth_headers, path, session_factory, config, outbox, workspace
):
    created = await make_link(client, auth_headers, path, email="Friend@Example.com", role="admin")
    assert created["token"] is None and created["link"] is None
    assert created["email"] == "friend@example.com"
    assert len(outbox) == 1 and outbox[0].to == "friend@example.com"
    token = outbox[0].text.split("#token=")[1].split()[0]
    assert workspace.name in outbox[0].text and "invited you" in outbox[0].text

    _, stranger = await person(session_factory, config, "stranger@example.com")
    assert_error(await accept(client, stranger, token), 404, "invalid_invitation")
    friend, friend_headers = await person(session_factory, config, "friend@example.com")
    joined = await accept(client, friend_headers, token)
    assert joined.status_code == 200 and joined.json()["role"] == "admin"


async def test_a_new_invitation_replaces_the_pending_one_for_the_address(
    client, auth_headers, path, session_factory, config, outbox, owner_engine
):
    for _ in range(2):
        await make_link(client, auth_headers, path, email="friend@example.com")
    first, second = (mail.text.split("#token=")[1].split()[0] for mail in outbox)
    _, friend = await person(session_factory, config, "friend@example.com")
    assert_error(await accept(client, friend, first), 404, "invalid_invitation")
    assert (await accept(client, friend, second)).status_code == 200
    reasons = await owner_query(
        owner_engine,
        "SELECT details->>'reason' FROM audit_events WHERE event = 'invitation_revoked'",
    )
    assert reasons == [("replaced",)]


async def test_inviting_an_existing_member_conflicts(client, auth_headers, path, test_user):
    response = await client.post(path, headers=auth_headers, json={"email": test_user.email})
    assert_error(response, 409, "already_member")


async def test_accepting_as_a_member_keeps_the_invitation_usable(
    client, auth_headers, path, session_factory, config
):
    token = (await make_link(client, auth_headers, path))["token"]
    assert_error(await accept(client, auth_headers, token), 409, "already_member")
    _, joiner = await person(session_factory, config, "joiner@example.com")
    assert (await accept(client, joiner, token)).status_code == 200


async def test_unverified_accounts_cannot_use_invitations(
    client, auth_headers, path, session_factory, config
):
    token = (await make_link(client, auth_headers, path))["token"]
    _, unverified = await person(session_factory, config, "unverified@example.com", verified=False)
    assert_error(await accept(client, unverified, token), 403, "email_verification_required")
    # Still usable by someone who may sign in.
    _, joiner = await person(session_factory, config, "joiner@example.com")
    assert (await accept(client, joiner, token)).status_code == 200


async def test_revoking(client, auth_headers, path, session_factory, config, owner_engine):
    invite = await make_link(client, auth_headers, path)
    url = f"{path}/{invite['id']}"
    assert (await client.delete(url, headers=auth_headers)).status_code == 204
    assert (await client.delete(url, headers=auth_headers)).status_code == 204  # idempotent
    accepted = await make_link(client, auth_headers, path)
    _, joiner = await person(session_factory, config, "joiner@example.com")
    await accept(client, joiner, accepted["token"])
    assert_error(
        await client.delete(f"{path}/{accepted['id']}", headers=auth_headers),
        409,
        "invitation_not_pending",
    )
    events = await owner_query(
        owner_engine, "SELECT event FROM audit_events WHERE event LIKE 'invitation_%'"
    )
    assert sorted(e[0] for e in events) == sorted(
        ["invitation_created", "invitation_revoked", "invitation_created", "invitation_accepted"]
    )


async def test_admin_invitation_can_only_be_made_by_the_owner(
    client, session_factory, config, owner_sessions, test_user, auth_headers, workspace
):
    admin, admin_headers = await person(session_factory, config, "admin@example.com")
    shared = await create_workspace(
        owner_sessions, test_user, name="Shared", members=((admin, WorkspaceRole.ADMIN),)
    )
    path = f"/v1/workspaces/{shared.id}/invitations"
    assert_error(
        await client.post(path, headers=admin_headers, json={"role": "admin"}),
        403,
        "insufficient_role",
    )
    assert (
        await client.post(path, headers=admin_headers, json={"role": "member"})
    ).status_code == 201


async def test_invitation_endpoints_are_rate_limited(client, auth_headers, path, app):
    from datetime import timedelta as td

    from app.core.ratelimit import Rule
    from app.modules.workspaces import limits

    app.state.rate_limiter.overrides[limits.INVITE_PER_ACCOUNT.name] = Rule(
        "invite_account", 2, td(hours=1)
    )
    statuses = [
        (await client.post(path, headers=auth_headers, json={})).status_code for _ in range(3)
    ]
    assert statuses == [201, 201, 429]


async def test_invitation_validation(client, auth_headers, path):
    for body in ({"email": "not-an-email"}, {"role": "owner"}, {"unknown": 1}):
        assert_error(
            await client.post(path, headers=auth_headers, json=body), 422, "validation_error"
        )
    bad = await client.post("/v1/invitations/accept", headers=auth_headers, json={"token": "x"})
    assert_error(bad, 422, "validation_error")
