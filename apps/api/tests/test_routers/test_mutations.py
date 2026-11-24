import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update

from app.core.idempotency import IdempotencyRecord
from app.core.security import create_access_token
from app.modules.auth.models import User
from app.modules.items.models import Item
from app.modules.items.service import ItemService
from tests.test_http_contract import assert_error


def keyed(headers, key="test-resource-key"):
    return {**headers, "Idempotency-Key": key}


async def test_replays_create_update_delete_and_profile(client, auth_headers):
    create_key = keyed(auth_headers, "create")
    create = await client.post("/v1/items", headers=create_key, json={"title": "first version"})
    assert create.status_code == 201
    item_id = create.json()["id"]
    path = f"/v1/items/{item_id}"
    update_key = keyed(auth_headers, "patch")
    edited = await client.patch(path, headers=update_key, json={"title": "second version"})
    assert edited.status_code == 200
    assert edited.json()["title"] == "second version"
    assert (await client.get(path, headers=auth_headers)).json() == edited.json()

    create_replay = await client.post(
        "/v1/items", headers=create_key, json={"title": "first version"}
    )
    assert create_replay.status_code == 201
    assert create_replay.json() == create.json()
    assert create_replay.headers["x-request-id"] != create.headers["x-request-id"]
    assert (
        await client.patch(path, headers=update_key, json={"title": "second version"})
    ).json() == edited.json()
    assert len((await client.get("/v1/items", headers=auth_headers)).json()["items"]) == 1

    delete_key = keyed(auth_headers, "delete")
    for _ in range(2):
        deleted = await client.delete(path, headers=delete_key)
        assert deleted.status_code == 204
        assert deleted.content == b""
    assert_error(await client.get(path, headers=auth_headers), 404, "item_not_found")

    profile_key = keyed(auth_headers, "profile")
    profile = await client.patch("/v1/auth/me", headers=profile_key, json={"name": "Updated"})
    assert profile.status_code == 200
    assert profile.json()["name"] == "Updated"
    assert (
        await client.patch("/v1/auth/me", headers=profile_key, json={"name": "Updated"})
    ).json() == profile.json()


async def test_rejects_key_reuse_for_another_payload_or_target(client, auth_headers):
    headers = keyed(auth_headers)
    created = await client.post("/v1/items", headers=headers, json={"title": "one"})
    assert created.status_code == 201
    mismatch = await client.post("/v1/items", headers=headers, json={"title": "two"})
    assert_error(mismatch, 422, "idempotency_mismatch")
    mismatch = await client.post("/v1/items?other=query", headers=headers, json={"title": "one"})
    assert_error(mismatch, 422, "idempotency_mismatch")
    mismatch = await client.patch(
        f"/v1/items/{created.json()['id']}", headers=headers, json={"title": "one"}
    )
    assert_error(mismatch, 422, "idempotency_mismatch")
    assert_error(
        await client.post("/v1/items", headers=keyed(auth_headers, "x" * 129), json={"title": "x"}),
        422,
        "invalid_idempotency_key",
    )
    assert_error(
        await client.post("/v1/items", headers=keyed(auth_headers, ""), json={"title": "x"}),
        422,
        "invalid_idempotency_key",
    )


async def test_same_key_is_independent_between_users(client, auth_headers, config, session_factory):
    async with session_factory.begin() as session:
        other = User(email="other@example.com", name="Other")
        session.add(other)
    token = create_access_token({"sub": str(other.id)}, config)
    other_headers = {"Authorization": f"Bearer {token}"}
    first = await client.post("/v1/items", headers=keyed(auth_headers), json={"title": "one"})
    second = await client.post("/v1/items", headers=keyed(other_headers), json={"title": "two"})
    assert second.status_code == first.status_code == 201
    assert second.json()["id"] != first.json()["id"]
    forbidden = await client.get(f"/v1/items/{first.json()['id']}", headers=other_headers)
    assert_error(forbidden, 403, "item_forbidden")


async def test_concurrent_duplicate_returns_conflict(client, auth_headers, monkeypatch):
    writes_flushed = asyncio.Event()
    finish_write = asyncio.Event()
    create_item = ItemService.create_item

    async def hold_after_write(self, user_id, data):
        item = await create_item(self, user_id, data)
        writes_flushed.set()
        await finish_write.wait()
        return item

    monkeypatch.setattr(ItemService, "create_item", hold_after_write)
    headers = keyed(auth_headers)
    async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
        first = tasks.create_task(client.post("/v1/items", headers=headers, json={"title": "one"}))
        await writes_flushed.wait()
        duplicate = await client.post("/v1/items", headers=headers, json={"title": "one"})
        assert_error(duplicate, 409, "idempotency_in_progress")
        finish_write.set()
    assert first.result().status_code == 201
    replay = await client.post("/v1/items", headers=headers, json={"title": "one"})
    assert replay.json() == first.result().json()
    assert len((await client.get("/v1/items", headers=auth_headers)).json()["items"]) == 1


async def test_expired_key_can_be_reused(client, auth_headers, session_factory):
    headers = keyed(auth_headers)
    first = await client.post("/v1/items", headers=headers, json={"title": "one"})
    assert first.status_code == 201
    async with session_factory.begin() as session:
        await session.execute(
            update(IdempotencyRecord).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    second = await client.post("/v1/items", headers=headers, json={"title": "two"})
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    replay = await client.post("/v1/items", headers=headers, json={"title": "two"})
    assert replay.json() == second.json()


async def test_failed_mutation_rolls_back_before_retry(
    client, auth_headers, session_factory, monkeypatch
):
    create_item = ItemService.create_item

    async def fail_after_insert(self, user_id, data):
        await create_item(self, user_id, data)
        raise RuntimeError("insert failed during request processing")

    headers = keyed(auth_headers)
    with monkeypatch.context() as patch:
        patch.setattr(ItemService, "create_item", fail_after_insert)
        failed = await client.post("/v1/items", headers=headers, json={"title": "before retry"})
        assert_error(failed, 500, "internal_error")
    async with session_factory() as session:
        assert await session.scalar(select(IdempotencyRecord)) is None
        assert await session.scalar(select(Item)) is None

    retried = await client.post("/v1/items", headers=headers, json={"title": "retry after failure"})
    assert retried.status_code == 201


async def test_pagination_ties_and_deleted_cursor_anchor(
    client, auth_headers, session_factory, test_user
):
    ids = sorted([uuid4() for _ in range(5)], reverse=True)
    async with session_factory.begin() as session:
        # Postgres now() is the same for every insert in this transaction.
        session.add_all(
            [Item(id=item_id, user_id=test_user.id, title=str(item_id)) for item_id in ids]
        )

    first = await client.get("/v1/items", params={"limit": 2}, headers=auth_headers)
    assert first.status_code == 200
    assert [item["id"] for item in first.json()["items"]] == list(map(str, ids[:2]))
    cursor = first.json()["next_cursor"]
    assert cursor
    assert (await client.delete(f"/v1/items/{ids[1]}", headers=auth_headers)).status_code == 204

    second = await client.get(
        "/v1/items", params={"limit": 2, "cursor": cursor}, headers=auth_headers
    )
    assert second.status_code == 200
    assert [item["id"] for item in second.json()["items"]] == list(map(str, ids[2:4]))

    last = await client.get(
        "/v1/items", params={"cursor": second.json()["next_cursor"]}, headers=auth_headers
    )
    assert [item["id"] for item in last.json()["items"]] == [str(ids[4])]
    assert last.json()["next_cursor"] is None

    for limit in (0, 101):
        assert_error(
            await client.get("/v1/items", params={"limit": limit}, headers=auth_headers),
            422,
            "validation_error",
        )
    assert_error(
        await client.get("/v1/items", params={"cursor": "not-a-cursor!"}, headers=auth_headers),
        422,
        "invalid_cursor",
    )
