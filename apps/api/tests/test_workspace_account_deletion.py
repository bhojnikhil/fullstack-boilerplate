"""Account deletion with workspaces (phase 4 hook)."""

from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import create_workspace, in_workspace, owner_query, person
from tests.test_http_contract import assert_error


async def test_sole_owner_of_a_shared_workspace_cannot_delete_the_account(
    client, auth_headers, session_factory, config, owner_sessions, test_user, owner_engine
):
    member, _ = await person(session_factory, config, "member@example.com")
    shared = await create_workspace(
        owner_sessions, test_user, members=((member, WorkspaceRole.MEMBER),)
    )
    solo = await create_workspace(owner_sessions, test_user, name="Solo")

    blocked = await client.delete("/v1/me", headers=auth_headers)
    error = assert_error(blocked, 409, "account_deletion_blocked")
    assert error["details"] == {
        "reason": "sole_workspace_owner",
        "workspace_ids": [str(shared.id)],
    }
    # Nothing was deleted, including the solo workspace.
    rows = await owner_query(owner_engine, "SELECT count(*) FROM workspaces")
    assert rows == [(2,)]

    # Transferring ownership unblocks it.
    transfer = await client.post(
        f"/v1/workspaces/{shared.id}/transfer-ownership",
        headers=auth_headers,
        json={"user_id": str(member.id)},
    )
    assert transfer.status_code == 204
    await client.post(
        "/v1/items", headers=in_workspace(auth_headers, shared), json={"title": "kept"}
    )
    await client.post("/v1/items", headers=in_workspace(auth_headers, solo), json={"title": "gone"})
    assert (await client.delete("/v1/me", headers=auth_headers)).status_code == 204

    # The solo workspace (and its items) went with the user; the shared one stays,
    # with the user's membership removed and their item kept without an author.
    remaining = await owner_query(owner_engine, "SELECT id FROM workspaces")
    assert remaining == [(shared.id,)]
    members = await owner_query(owner_engine, "SELECT user_id, role FROM memberships")
    assert members == [(member.id, "owner")]
    items = await owner_query(owner_engine, "SELECT title, created_by_id FROM items")
    assert items == [("kept", None)]
    events = await owner_query(
        owner_engine,
        "SELECT details->>'reason' FROM audit_events WHERE event = 'workspace_deleted'",
    )
    assert events == [("account_deleted",)]


async def test_admin_can_delete_the_account_and_the_workspace_carries_on(
    client, auth_headers, session_factory, config, owner_sessions, test_user
):
    admin, admin_headers = await person(session_factory, config, "admin@example.com")
    workspace = await create_workspace(
        owner_sessions, test_user, members=((admin, WorkspaceRole.ADMIN),)
    )
    assert (await client.delete("/v1/me", headers=admin_headers)).status_code == 204
    members = await client.get(f"/v1/workspaces/{workspace.id}/members", headers=auth_headers)
    assert [m["role"] for m in members.json()["items"]] == ["owner"]
