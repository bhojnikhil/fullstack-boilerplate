"""Workspaces, members and roles: behavior, the permission matrix and the one-owner rule."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import bearer, create_workspace, in_workspace, owner_query, person, sign_in
from tests.test_http_contract import assert_error

OWNER, ADMIN, MEMBER = WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER


@pytest.fixture
async def team(client, session_factory, config, owner_sessions, test_user, auth_headers):
    """A workspace with an owner, an admin, a member and one spare of each (targets)."""
    users = {}
    for name in ("admin", "member", "spare_admin", "spare_member"):
        users[name] = await person(session_factory, config, f"{name}@example.com")
    workspace = await create_workspace(
        owner_sessions,
        test_user,
        members=(
            (users["admin"][0], ADMIN),
            (users["member"][0], MEMBER),
            (users["spare_admin"][0], ADMIN),
            (users["spare_member"][0], MEMBER),
        ),
    )

    class Team:
        pass

    team = Team()
    team.workspace = workspace
    team.path = f"/v1/workspaces/{workspace.id}"
    team.headers = {OWNER: auth_headers, ADMIN: users["admin"][1], MEMBER: users["member"][1]}
    team.users = {OWNER: test_user, ADMIN: users["admin"][0], MEMBER: users["member"][0]}
    team.spare_admin = users["spare_admin"][0]
    team.spare_member = users["spare_member"][0]
    return team


async def test_create_list_and_get_workspace(client, auth_headers):
    assert (await client.get("/v1/workspaces", headers=auth_headers)).json()["items"] == []
    created = await client.post(
        "/v1/workspaces",
        headers=auth_headers,
        json={"name": "  Our Home  ", "currency": "eur", "timezone": "Europe/Berlin"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Our Home"
    assert body["role"] == "owner"
    assert (body["currency"], body["timezone"]) == ("EUR", "Europe/Berlin")
    assert body["slug"].startswith("our-home-")
    listed = (await client.get("/v1/workspaces", headers=auth_headers)).json()["items"]
    assert [item["id"] for item in listed] == [body["id"]]
    fetched = await client.get(f"/v1/workspaces/{body['id']}", headers=auth_headers)
    assert fetched.json() == body


@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"name": "x" * 101},
        {"name": "Bad\x00name"},
        {"name": "Ok", "currency": "ZZZ"},
        {"name": "Ok", "currency": "US"},
        {"name": "Ok", "timezone": "Mars/Base"},
        {"name": "Ok", "slug": "Bad Slug"},
        {"name": "Ok", "slug": "ab"},
        {"name": "Ok", "slug": "double--hyphen"},
        {"name": "Ok", "extra": 1},
    ],
)
async def test_workspace_input_is_validated(client, auth_headers, payload):
    assert_error(
        await client.post("/v1/workspaces", headers=auth_headers, json=payload),
        422,
        "validation_error",
    )


async def test_slug_must_be_unique_on_create_and_update(client, auth_headers, team, config):
    body = {"name": "Other", "slug": "taken-slug"}
    assert (await client.post("/v1/workspaces", headers=auth_headers, json=body)).status_code == 201
    assert_error(
        await client.post("/v1/workspaces", headers=auth_headers, json=body),
        409,
        "workspace_slug_taken",
    )
    clash = await client.patch(team.path, headers=auth_headers, json={"slug": "taken-slug"})
    assert_error(clash, 409, "workspace_slug_taken")
    ok = await client.patch(
        team.path, headers=auth_headers, json={"slug": "fresh-slug", "name": "N"}
    )
    assert ok.json()["slug"] == "fresh-slug"
    assert ok.json()["name"] == "N"


async def test_owned_workspace_limit(client, auth_headers, monkeypatch):
    from app.modules.workspaces import service

    monkeypatch.setattr(service, "MAX_OWNED_WORKSPACES", 2)
    for index in range(2):
        created = await client.post(
            "/v1/workspaces", headers=auth_headers, json={"name": f"W{index}"}
        )
        assert created.status_code == 201
    assert_error(
        await client.post("/v1/workspaces", headers=auth_headers, json={"name": "W3"}),
        409,
        "workspace_limit_reached",
    )


async def test_pagination_of_workspaces_and_members(client, auth_headers, team):
    for index in range(2):
        await client.post("/v1/workspaces", headers=auth_headers, json={"name": f"Extra {index}"})
    first = (await client.get("/v1/workspaces?limit=2", headers=auth_headers)).json()
    second = (
        await client.get(
            f"/v1/workspaces?limit=2&cursor={first['next_cursor']}", headers=auth_headers
        )
    ).json()
    ids = [item["id"] for item in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 3 and second["next_cursor"] is None
    page = (await client.get(f"{team.path}/members?limit=2", headers=auth_headers)).json()
    rest = (
        await client.get(
            f"{team.path}/members?limit=10&cursor={page['next_cursor']}", headers=auth_headers
        )
    ).json()
    assert len(page["items"]) == 2 and len(rest["items"]) == 3


async def test_member_emails_are_visible_to_admins_only(client, team):
    for role, visible in ((OWNER, True), (ADMIN, True), (MEMBER, False)):
        members = (await client.get(f"{team.path}/members", headers=team.headers[role])).json()
        emails = [member["email"] for member in members["items"]]
        assert all((email is not None) is visible for email in emails), role


# --- permission matrix -------------------------------------------------------------------

# action -> (method, path suffix builder, json builder, {role: expected status})
ACTIONS = {
    "get": ("GET", lambda t: "", None, {OWNER: 200, ADMIN: 200, MEMBER: 200}),
    "update": (
        "PATCH",
        lambda t: "",
        lambda t: {"name": "Renamed"},
        {OWNER: 200, ADMIN: 200, MEMBER: 403},
    ),
    "list_members": ("GET", lambda t: "/members", None, {OWNER: 200, ADMIN: 200, MEMBER: 200}),
    "change_role": (
        "PATCH",
        lambda t: f"/members/{t.spare_member.id}",
        lambda t: {"role": "admin"},
        {OWNER: 204, ADMIN: 403, MEMBER: 403},
    ),
    "remove_member": (
        "DELETE",
        lambda t: f"/members/{t.spare_member.id}",
        None,
        {OWNER: 204, ADMIN: 204, MEMBER: 403},
    ),
    "remove_admin": (
        "DELETE",
        lambda t: f"/members/{t.spare_admin.id}",
        None,
        {OWNER: 204, ADMIN: 403, MEMBER: 403},
    ),
    "invite_member": (
        "POST",
        lambda t: "/invitations",
        lambda t: {"role": "member"},
        {OWNER: 201, ADMIN: 201, MEMBER: 403},
    ),
    "invite_admin": (
        "POST",
        lambda t: "/invitations",
        lambda t: {"role": "admin"},
        {OWNER: 201, ADMIN: 403, MEMBER: 403},
    ),
    "list_invitations": (
        "GET",
        lambda t: "/invitations",
        None,
        {OWNER: 200, ADMIN: 200, MEMBER: 403},
    ),
    "transfer": (
        "POST",
        lambda t: "/transfer-ownership",
        lambda t: {"user_id": str(t.spare_admin.id)},
        {OWNER: 204, ADMIN: 403, MEMBER: 403},
    ),
    "leave": ("POST", lambda t: "/leave", None, {OWNER: 409, ADMIN: 204, MEMBER: 204}),
    "delete": ("DELETE", lambda t: "", None, {OWNER: 204, ADMIN: 403, MEMBER: 403}),
}


@pytest.mark.parametrize(
    ("action", "role"), [(a, r) for a, spec in ACTIONS.items() for r in spec[3]]
)
async def test_role_permission_matrix(client, team, action, role):
    method, suffix, body, expected = ACTIONS[action]
    response = await client.request(
        method,
        team.path + suffix(team),
        headers=team.headers[role],
        json=body(team) if body else None,
    )
    assert response.status_code == expected[role], response.text
    if expected[role] == 403:
        assert response.json()["error"]["code"] == "insufficient_role"


# --- ownership ---------------------------------------------------------------------------


async def test_transfer_makes_one_new_owner_and_demotes_the_old(client, team, owner_engine):
    response = await client.post(
        f"{team.path}/transfer-ownership",
        headers=team.headers[OWNER],
        json={"user_id": str(team.users[ADMIN].id)},
    )
    assert response.status_code == 204
    rows = await owner_query(
        owner_engine,
        "SELECT user_id, role FROM memberships WHERE workspace_id = :w AND role = 'owner'",
        w=team.workspace.id,
    )
    assert [row[0] for row in rows] == [team.users[ADMIN].id]
    old = await client.get(team.path, headers=team.headers[OWNER])
    assert old.json()["role"] == "admin"
    new = await client.get(team.path, headers=team.headers[ADMIN])
    assert new.json()["role"] == "owner"
    # The former owner can no longer do owner things.
    again = await client.delete(team.path, headers=team.headers[OWNER])
    assert_error(again, 403, "insufficient_role")
    audit = await owner_query(
        owner_engine, "SELECT details FROM audit_events WHERE event = 'ownership_transferred'"
    )
    assert audit[0][0]["new_owner_id"] == str(team.users[ADMIN].id)


async def test_transfer_to_self_or_non_member_is_rejected(client, team):
    path = f"{team.path}/transfer-ownership"
    mine = await client.post(
        path, headers=team.headers[OWNER], json={"user_id": str(team.users[OWNER].id)}
    )
    assert_error(mine, 409, "owner_protected")
    stranger = await client.post(path, headers=team.headers[OWNER], json={"user_id": str(uuid4())})
    assert_error(stranger, 404, "member_not_found")


async def test_transfer_and_delete_need_a_recent_sign_in(client, team, session_factory, config):
    stale = bearer(
        await sign_in(
            session_factory,
            config,
            team.users[OWNER],
            authenticated_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    for method, suffix, body in (
        ("POST", "/transfer-ownership", {"user_id": str(team.users[ADMIN].id)}),
        ("DELETE", "", None),
    ):
        response = await client.request(method, team.path + suffix, headers=stale, json=body)
        assert_error(response, 403, "reauthentication_required")


async def test_owner_cannot_be_demoted_removed_or_leave(client, team):
    owner = team.users[OWNER].id
    demote = await client.patch(
        f"{team.path}/members/{owner}", headers=team.headers[OWNER], json={"role": "member"}
    )
    assert_error(demote, 409, "owner_protected")
    remove = await client.delete(f"{team.path}/members/{owner}", headers=team.headers[ADMIN])
    assert_error(remove, 409, "owner_protected")
    assert_error(
        await client.post(f"{team.path}/leave", headers=team.headers[OWNER]),
        409,
        "owner_cannot_leave",
    )
    invalid = await client.patch(
        f"{team.path}/members/{team.users[MEMBER].id}",
        headers=team.headers[OWNER],
        json={"role": "owner"},
    )
    assert_error(invalid, 422, "validation_error")


async def test_database_enforces_exactly_one_owner(owner_engine, team):
    workspace, member = team.workspace.id, team.users[MEMBER].id

    async def attempt(*statements):
        async with owner_engine.connect() as connection:
            try:
                for statement in statements:
                    await connection.execute(text(statement), {"w": workspace, "u": member})
                await connection.commit()
            except DBAPIError:
                return True
            return False

    # A second owner row is refused immediately by the partial unique index.
    assert await attempt(
        "UPDATE memberships SET role = 'owner' WHERE workspace_id = :w AND user_id = :u"
    )
    # Without a new owner named, demoting or deleting the owner fails at commit.
    assert await attempt(
        "UPDATE memberships SET role = 'admin' WHERE workspace_id = :w AND role = 'owner'"
    )
    assert await attempt("DELETE FROM memberships WHERE workspace_id = :w AND role = 'owner'")
    # Pointing the workspace at a member who is not the owner fails at commit.
    assert await attempt("UPDATE workspaces SET owner_id = :u WHERE id = :w")
    # A consistent hand-over in one transaction is fine.
    assert not await attempt(
        "UPDATE memberships SET role = 'admin' WHERE workspace_id = :w AND role = 'owner'",
        "UPDATE memberships SET role = 'owner' WHERE workspace_id = :w AND user_id = :u",
        "UPDATE workspaces SET owner_id = :u WHERE id = :w",
    )


# --- members -----------------------------------------------------------------------------


async def test_change_role_remove_and_leave_update_membership(client, team, owner_engine):
    target = team.users[MEMBER].id
    await client.patch(
        f"{team.path}/members/{target}", headers=team.headers[OWNER], json={"role": "admin"}
    )
    assert (await client.get(team.path, headers=team.headers[MEMBER])).json()["role"] == "admin"
    assert (
        await client.delete(f"{team.path}/members/{target}", headers=team.headers[OWNER])
    ).status_code == 204
    # Removed members lose access entirely (404, as for any outsider).
    assert_error(
        await client.get(team.path, headers=team.headers[MEMBER]), 404, "workspace_not_found"
    )
    assert_error(
        await client.delete(f"{team.path}/members/{target}", headers=team.headers[OWNER]),
        404,
        "member_not_found",
    )
    assert (await client.post(f"{team.path}/leave", headers=team.headers[ADMIN])).status_code == 204
    assert_error(
        await client.get(team.path, headers=team.headers[ADMIN]), 404, "workspace_not_found"
    )
    events = await owner_query(owner_engine, "SELECT event FROM audit_events ORDER BY created_at")
    names = {row[0] for row in events}
    assert {"member_role_changed", "member_removed", "member_left"} <= names


async def test_audit_events_carry_ids_only(client, team, owner_engine):
    await client.patch(
        f"{team.path}/members/{team.users[MEMBER].id}",
        headers=team.headers[OWNER],
        json={"role": "admin"},
    )
    await client.delete(f"{team.path}/members/{team.spare_member.id}", headers=team.headers[OWNER])
    rows = await owner_query(
        owner_engine, "SELECT details FROM audit_events WHERE event LIKE 'member_%'"
    )
    assert rows
    for (details,) in rows:
        assert "@" not in str(details) and "example.com" not in str(details)
        assert set(details) <= {"workspace_id", "target_user_id", "from_role", "to_role", "role"}


async def test_replayed_leave_returns_the_stored_response(client, team):
    headers = {**team.headers[MEMBER], "Idempotency-Key": "leave-1"}
    assert (await client.post(f"{team.path}/leave", headers=headers)).status_code == 204
    # The retry arrives after the first call committed; it is a replay, not a 404.
    assert (await client.post(f"{team.path}/leave", headers=headers)).status_code == 204


async def test_delete_workspace_removes_everything_in_it(client, team, owner_engine):
    headers = in_workspace(team.headers[OWNER], team.workspace)
    await client.post("/v1/items", headers=headers, json={"title": "gone"})
    await client.post(f"{team.path}/invitations", headers=team.headers[OWNER], json={})
    assert (await client.delete(team.path, headers=team.headers[OWNER])).status_code == 204
    for table in ("items", "memberships", "invitations"):
        rows = await owner_query(
            owner_engine, f"SELECT 1 FROM {table} WHERE workspace_id = :w", w=team.workspace.id
        )
        assert rows == []
    assert_error(
        await client.get(team.path, headers=team.headers[OWNER]), 404, "workspace_not_found"
    )


async def test_ready_refuses_a_database_role_that_bypasses_row_level_security(
    config, owner_engine, test_db_engine
):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.factory import create_app

    config.env = "staging"

    async def probe(engine):
        app = create_app(config, async_sessionmaker(engine, expire_on_commit=False))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as c:
            return await c.get("/ready")

    assert (await probe(test_db_engine)).status_code == 200
    assert_error(await probe(owner_engine), 503, "not_ready")
