"""Tenant isolation: a member of workspace A gets 404 for everything in workspace B.

Routes are discovered from the application's route table: every route whose dependencies
include a workspace resolver must have a case in ``CASES`` (and the reverse), so a new
workspace-scoped route fails this suite until someone writes its isolation case.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

from app.modules.workspaces.dependencies import WORKSPACE_RESOLVERS
from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import create_workspace, in_workspace, person
from tests.test_http_contract import assert_error


@dataclass
class World:
    """Alice owns workspace A; Bob owns workspace B, which holds an item and an invitation."""

    client: object
    alice: dict[str, str]
    a: object
    b: object
    bob: object
    b_item: str
    b_invitation: str

    def a_headers(self) -> dict[str, str]:
        return in_workspace(self.alice, self.a)

    def b_headers(self) -> dict[str, str]:
        return in_workspace(self.alice, self.b)  # Alice naming Bob's workspace


@pytest.fixture
async def world(client, session_factory, config, owner_sessions, test_user, auth_headers):
    bob, bob_headers = await person(session_factory, config, "bob@example.com")
    a = await create_workspace(owner_sessions, test_user, name="A")
    b = await create_workspace(owner_sessions, bob, name="B")
    item = await client.post(
        "/v1/items", headers=in_workspace(bob_headers, b), json={"title": "bob's secret"}
    )
    invitation = await client.post(
        f"/v1/workspaces/{b.id}/invitations", headers=bob_headers, json={}
    )
    return World(client, auth_headers, a, b, bob, item.json()["id"], invitation.json()["id"])


Case = Callable[[World], Awaitable[list[tuple[object, str]]]]


async def responses(*pending) -> list:
    return [await call for call in pending]


def foreign(world: World, suffix: str = "") -> str:
    return f"/v1/workspaces/{world.b.id}{suffix}"


# Each case issues requests that must all answer 404 with the paired error code.
CASES: dict[tuple[str, str], Callable[[World], list]] = {
    ("GET", "/v1/items"): lambda w: [
        (w.client.get("/v1/items", headers=w.b_headers()), "workspace_not_found")
    ],
    ("POST", "/v1/items"): lambda w: [
        (
            w.client.post("/v1/items", headers=w.b_headers(), json={"title": "x"}),
            "workspace_not_found",
        )
    ],
    ("GET", "/v1/items/{item_id}"): lambda w: [
        (w.client.get(f"/v1/items/{w.b_item}", headers=w.b_headers()), "workspace_not_found"),
        # Right workspace, someone else's item id.
        (w.client.get(f"/v1/items/{w.b_item}", headers=w.a_headers()), "item_not_found"),
    ],
    ("PATCH", "/v1/items/{item_id}"): lambda w: [
        (
            w.client.patch(f"/v1/items/{w.b_item}", headers=w.b_headers(), json={"title": "x"}),
            "workspace_not_found",
        ),
        (
            w.client.patch(f"/v1/items/{w.b_item}", headers=w.a_headers(), json={"title": "x"}),
            "item_not_found",
        ),
    ],
    ("DELETE", "/v1/items/{item_id}"): lambda w: [
        (w.client.delete(f"/v1/items/{w.b_item}", headers=w.b_headers()), "workspace_not_found"),
        (w.client.delete(f"/v1/items/{w.b_item}", headers=w.a_headers()), "item_not_found"),
    ],
    ("GET", "/v1/workspaces/{workspace_id}"): lambda w: [
        (w.client.get(foreign(w), headers=w.alice), "workspace_not_found")
    ],
    ("PATCH", "/v1/workspaces/{workspace_id}"): lambda w: [
        (
            w.client.patch(foreign(w), headers=w.alice, json={"name": "mine now"}),
            "workspace_not_found",
        )
    ],
    ("DELETE", "/v1/workspaces/{workspace_id}"): lambda w: [
        (w.client.delete(foreign(w), headers=w.alice), "workspace_not_found")
    ],
    ("GET", "/v1/workspaces/{workspace_id}/members"): lambda w: [
        (w.client.get(foreign(w, "/members"), headers=w.alice), "workspace_not_found")
    ],
    ("PATCH", "/v1/workspaces/{workspace_id}/members/{user_id}"): lambda w: [
        (
            w.client.patch(
                foreign(w, f"/members/{w.bob.id}"), headers=w.alice, json={"role": "admin"}
            ),
            "workspace_not_found",
        ),
        # Own workspace, a user who is only a member of B.
        (
            w.client.patch(
                f"/v1/workspaces/{w.a.id}/members/{w.bob.id}",
                headers=w.alice,
                json={"role": "admin"},
            ),
            "member_not_found",
        ),
    ],
    ("DELETE", "/v1/workspaces/{workspace_id}/members/{user_id}"): lambda w: [
        (
            w.client.delete(foreign(w, f"/members/{w.bob.id}"), headers=w.alice),
            "workspace_not_found",
        ),
        (
            w.client.delete(f"/v1/workspaces/{w.a.id}/members/{w.bob.id}", headers=w.alice),
            "member_not_found",
        ),
    ],
    ("POST", "/v1/workspaces/{workspace_id}/leave"): lambda w: [
        (w.client.post(foreign(w, "/leave"), headers=w.alice), "workspace_not_found")
    ],
    ("POST", "/v1/workspaces/{workspace_id}/transfer-ownership"): lambda w: [
        (
            w.client.post(
                foreign(w, "/transfer-ownership"), headers=w.alice, json={"user_id": str(uuid4())}
            ),
            "workspace_not_found",
        )
    ],
    ("POST", "/v1/workspaces/{workspace_id}/invitations"): lambda w: [
        (w.client.post(foreign(w, "/invitations"), headers=w.alice, json={}), "workspace_not_found")
    ],
    ("GET", "/v1/workspaces/{workspace_id}/invitations"): lambda w: [
        (w.client.get(foreign(w, "/invitations"), headers=w.alice), "workspace_not_found")
    ],
    ("DELETE", "/v1/workspaces/{workspace_id}/invitations/{invitation_id}"): lambda w: [
        (
            w.client.delete(foreign(w, f"/invitations/{w.b_invitation}"), headers=w.alice),
            "workspace_not_found",
        ),
        (
            w.client.delete(
                f"/v1/workspaces/{w.a.id}/invitations/{w.b_invitation}", headers=w.alice
            ),
            "invitation_not_found",
        ),
    ],
}


def flatten(routes):
    """(method, path, dependant) for every API route, through nested routers.

    FastAPI nests included routers lazily (``effective_candidates``); this reads that
    structure, so a FastAPI upgrade that changes it fails the discovery test loudly.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                yield method, route.path, route.dependant
        elif hasattr(route, "effective_candidates"):
            yield from flatten(route.effective_candidates())
        elif hasattr(route, "original_route") and isinstance(route.original_route, APIRoute):
            for method in route.original_route.methods:
                yield method, route.path, route.original_route.dependant


def discovered_routes(app) -> set[tuple[str, str]]:
    def depends_on_resolver(dependant) -> bool:
        return dependant.call in WORKSPACE_RESOLVERS or any(
            depends_on_resolver(child) for child in dependant.dependencies
        )

    return {
        (method, path)
        for method, path, dependant in flatten(app.routes)
        if depends_on_resolver(dependant)
    }


def test_every_workspace_scoped_route_has_an_isolation_case(app):
    routes = discovered_routes(app)
    assert routes, "route discovery found nothing"
    assert routes - set(CASES) == set(), "add an isolation case for the new route(s)"
    assert set(CASES) - routes == set(), "isolation cases for routes that no longer exist"


def test_discovery_sees_a_new_workspace_route(app):
    from app.modules.workspaces.dependencies import ActiveWorkspace

    @app.get("/v1/new-tenant-thing")
    async def new_route(workspace: ActiveWorkspace) -> dict[str, str]:
        return {}

    assert ("GET", "/v1/new-tenant-thing") in discovered_routes(app)


@pytest.mark.parametrize(("method", "path"), sorted(CASES))
async def test_member_of_a_gets_404_for_bs_resources(world, method, path):
    for pending, code in CASES[(method, path)](world):
        response = await pending
        assert_error(response, 404, code)
        # Nothing about B leaks into the message.
        assert str(world.b.id) not in response.text or "workspace_id" in path


async def test_responses_for_missing_and_foreign_workspaces_are_identical(world):
    """Non-existent and foreign workspaces cannot be told apart."""
    foreign_response = await world.client.get(f"/v1/workspaces/{world.b.id}", headers=world.alice)
    missing_response = await world.client.get(f"/v1/workspaces/{uuid4()}", headers=world.alice)
    assert foreign_response.status_code == missing_response.status_code == 404
    assert foreign_response.json() == missing_response.json()
    header_foreign = await world.client.get("/v1/items", headers=world.b_headers())
    header_missing = await world.client.get(
        "/v1/items", headers={**world.alice, "X-Workspace-Id": str(uuid4())}
    )
    garbage = await world.client.get("/v1/items", headers={**world.alice, "X-Workspace-Id": "nope"})
    assert header_foreign.json() == header_missing.json() == garbage.json()


async def test_missing_workspace_header_is_a_client_error(world):
    assert_error(
        await world.client.get("/v1/items", headers=world.alice), 400, "workspace_required"
    )


async def test_lists_only_show_the_callers_own_data(world, owner_sessions, test_user):
    listed = (await world.client.get("/v1/workspaces", headers=world.alice)).json()["items"]
    assert [item["id"] for item in listed] == [str(world.a.id)]
    items = (await world.client.get("/v1/items", headers=world.a_headers())).json()["items"]
    assert items == []


async def test_leaving_a_workspace_revokes_access_to_its_items(world, owner_sessions, test_user):
    shared = await create_workspace(
        owner_sessions, world.bob, name="Shared", members=((test_user, WorkspaceRole.MEMBER),)
    )
    headers = in_workspace(world.alice, shared)
    assert (
        await world.client.post("/v1/items", headers=headers, json={"title": "t"})
    ).status_code == 201
    assert (
        await world.client.post(f"/v1/workspaces/{shared.id}/leave", headers=world.alice)
    ).status_code == 204
    assert_error(await world.client.get("/v1/items", headers=headers), 404, "workspace_not_found")
