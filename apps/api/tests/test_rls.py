"""Row-level security, exercised directly as the application's (non-owner) database role.

These tests bypass every application filter: raw SQL with only the per-transaction
settings the API would set. Seeding is done as the owner.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core import rls
from app.core.security import token_digest
from app.modules.items.models import Item
from tests.conftest import create_user, create_workspace

TABLES = ("workspaces", "memberships", "invitations", "items")


@pytest.fixture
async def seeded(owner_sessions, session_factory, test_db_engine):
    alice = await create_user(session_factory, email="alice@example.com")
    bob = await create_user(session_factory, email="bob@example.com")
    a = await create_workspace(owner_sessions, alice, name="A")
    b = await create_workspace(owner_sessions, bob, name="B")
    async with owner_sessions.begin() as db:
        for workspace, owner in ((a, alice), (b, bob)):
            db.add(
                Item(
                    workspace_id=workspace.id,
                    created_by_id=owner.id,
                    title=f"item {workspace.name}",
                )
            )
        await db.execute(
            text(
                "INSERT INTO invitations (id, workspace_id, role, token_hash, expires_at, invited_by_id) "
                "VALUES (gen_random_uuid(), :w, 'member', :h, now() + interval '1 day', :u)"
            ),
            {"w": b.id, "h": token_digest("bobs-invitation-token"), "u": bob.id},
        )
    return type("Seed", (), {"alice": alice, "bob": bob, "a": a, "b": b})


async def scoped(engine, *, user=None, workspace=None, invitation=None):
    """A connection in a transaction with the given settings, as the app would set them."""
    connection = await engine.connect()
    await connection.begin()
    for name, value in (
        (rls.USER_ID, user),
        (rls.WORKSPACE_ID, workspace),
        (rls.INVITATION_HASH, invitation),
    ):
        if value is not None:
            await connection.execute(
                text("SELECT set_config(:n, :v, true)"), {"n": name, "v": str(value)}
            )
    return connection


async def count(connection, table, where="true"):
    return await connection.scalar(text(f"SELECT count(*) FROM {table} WHERE {where}"))


async def test_the_test_role_is_not_the_owner_and_cannot_bypass_rls(test_db_engine):
    async with test_db_engine.connect() as connection:
        flags = (
            await connection.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).one()
        owned = await connection.scalar(
            text(
                "SELECT count(*) FROM pg_tables WHERE schemaname = current_schema() AND tableowner = current_user"
            )
        )
    assert tuple(flags) == (False, False) and owned == 0


@pytest.mark.parametrize("table", TABLES)
async def test_no_settings_means_no_rows(test_db_engine, seeded, table):
    connection = await scoped(test_db_engine)
    try:
        assert await count(connection, table) == 0
    finally:
        await connection.close()


async def test_alice_sees_only_her_workspaces_rows(test_db_engine, seeded):
    connection = await scoped(test_db_engine, user=seeded.alice.id, workspace=seeded.a.id)
    try:
        assert await count(connection, "items") == 1
        assert await count(connection, "items", f"workspace_id = '{seeded.b.id}'") == 0
        assert await count(connection, "workspaces", f"id = '{seeded.b.id}'") == 0
        assert await count(connection, "memberships", f"workspace_id = '{seeded.b.id}'") == 0
        assert await count(connection, "invitations") == 0
        assert await count(connection, "workspaces") == 1
    finally:
        await connection.close()


async def test_naming_a_foreign_workspace_still_yields_no_items(test_db_engine, seeded):
    # Items also require the user's own membership, independent of the setting.
    connection = await scoped(test_db_engine, user=seeded.alice.id, workspace=seeded.b.id)
    try:
        assert await count(connection, "items") == 0
    finally:
        await connection.close()


async def test_membership_list_without_workspace_is_the_users_own(test_db_engine, seeded):
    connection = await scoped(test_db_engine, user=seeded.alice.id)
    try:
        rows = (await connection.execute(text("SELECT workspace_id FROM memberships"))).all()
        listed = (await connection.execute(text("SELECT id FROM workspaces"))).all()
    finally:
        await connection.close()
    assert [r[0] for r in rows] == [seeded.a.id] and [r[0] for r in listed] == [seeded.a.id]


async def test_an_invitation_is_visible_only_with_its_token_digest(test_db_engine, seeded):
    connection = await scoped(
        test_db_engine, user=seeded.alice.id, invitation=token_digest("bobs-invitation-token")
    )
    try:
        assert await count(connection, "invitations") == 1
    finally:
        await connection.close()
    wrong = await scoped(test_db_engine, user=seeded.alice.id, invitation=token_digest("guess"))
    try:
        assert await count(wrong, "invitations") == 0
    finally:
        await wrong.close()


async def test_writes_into_foreign_workspaces_are_refused(test_db_engine, seeded):
    statements = [
        "INSERT INTO items (id, workspace_id, title, is_active) VALUES (gen_random_uuid(), :b, 't', true)",
        "INSERT INTO memberships (id, workspace_id, user_id, role) VALUES (gen_random_uuid(), :b, :a, 'member')",
        "INSERT INTO memberships (id, workspace_id, user_id, role) VALUES (gen_random_uuid(), :a, :bob, 'member')",
        "INSERT INTO memberships (id, workspace_id, user_id, role) VALUES (gen_random_uuid(), :a, :a, 'member')",
    ]
    for statement in statements:
        connection = await scoped(test_db_engine, user=seeded.alice.id, workspace=seeded.a.id)
        try:
            with pytest.raises(DBAPIError, match="row-level security"):
                await connection.execute(
                    text(statement),
                    {"a": seeded.alice.id, "b": seeded.b.id, "bob": seeded.bob.id},
                )
        finally:
            await connection.close()
    for statement in (
        "UPDATE items SET title = 'hijacked' WHERE workspace_id = :b",
        "DELETE FROM items WHERE workspace_id = :b",
        "UPDATE workspaces SET name = 'hijacked' WHERE id = :b",
        "DELETE FROM memberships WHERE workspace_id = :b",
        "UPDATE memberships SET role = 'owner' WHERE workspace_id = :b",
    ):
        connection = await scoped(test_db_engine, user=seeded.alice.id, workspace=seeded.a.id)
        try:
            assert (await connection.execute(text(statement), {"b": seeded.b.id})).rowcount == 0
        finally:
            await connection.close()


async def test_joining_requires_a_usable_invitation_for_that_role(
    test_db_engine, seeded, owner_sessions
):
    insert = text(
        "INSERT INTO memberships (id, workspace_id, user_id, role) "
        "VALUES (gen_random_uuid(), :w, :u, :r)"
    )
    digest = token_digest("bobs-invitation-token")

    async def join(role="member"):
        connection = await scoped(
            test_db_engine, user=seeded.alice.id, workspace=seeded.b.id, invitation=digest
        )
        try:
            await connection.execute(insert, {"w": seeded.b.id, "u": seeded.alice.id, "r": role})
        finally:
            await connection.close()

    with pytest.raises(DBAPIError, match="row-level security"):
        await join("admin")  # The invitation grants member, not admin.
    await join("member")  # Rolled back on close; the policy accepted it.
    async with owner_sessions.begin() as db:
        await db.execute(text("UPDATE invitations SET revoked_at = now()"))
    with pytest.raises(DBAPIError, match="row-level security"):
        await join("member")


async def test_every_table_with_a_workspace_column_has_forced_rls_and_policies(owner_engine):
    async with owner_engine.connect() as connection:
        tenant = {
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND column_name = 'workspace_id'"
                )
            )
        } | {"workspaces"}
        flags = {
            row[0]: (row[1], row[2])
            for row in await connection.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
                    "WHERE c.relnamespace = current_schema()::regnamespace AND c.relkind = 'r'"
                )
            )
        }
        policies = {
            row[0]
            for row in await connection.execute(
                text(
                    "SELECT DISTINCT tablename FROM pg_policies WHERE schemaname = current_schema()"
                )
            )
        }
    assert tenant >= set(TABLES)
    for table in tenant:
        assert flags[table] == (True, True), f"{table} needs ENABLE and FORCE ROW LEVEL SECURITY"
        assert table in policies, f"{table} has no policy"


async def test_session_settings_survive_a_mid_request_commit(session_factory, seeded):
    async with session_factory() as db:
        await rls.bind(db, rls.USER_ID, str(seeded.alice.id))
        await rls.bind(db, rls.WORKSPACE_ID, str(seeded.a.id))
        assert (await db.execute(text("SELECT count(*) FROM items"))).scalar() == 1
        await db.commit()
        assert (await db.execute(text("SELECT count(*) FROM items"))).scalar() == 1
        await rls.bind(db, rls.WORKSPACE_ID, None)
        assert (await db.execute(text("SELECT count(*) FROM items"))).scalar() == 0


def test_tenant_repositories_require_a_workspace_id():
    from app.core.tenancy import TenantRepository
    from app.modules.items.repository import ItemRepository

    with pytest.raises(TypeError):
        ItemRepository(None)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        TenantRepository(None, "not-a-uuid")  # type: ignore[arg-type]
    assert ItemRepository(None, uuid4()).workspace_id  # type: ignore[arg-type]


# --- R1-1: a setting alone is never enough ----------------------------------------------

READS = {
    "workspaces": "id = :b",
    "memberships": "workspace_id = :b",
    "invitations": "workspace_id = :b",
    "items": "workspace_id = :b",
}
INSERTS = {
    "workspaces": "INSERT INTO workspaces (id, name, slug, currency, timezone, owner_id) "
    "VALUES (gen_random_uuid(), 'x', 'slug-' || gen_random_uuid(), 'USD', 'UTC', :alice)",
    "memberships": "INSERT INTO memberships (id, workspace_id, user_id, role) "
    "VALUES (gen_random_uuid(), :b, :alice, 'member')",
    "memberships (as owner)": "INSERT INTO memberships (id, workspace_id, user_id, role) "
    "VALUES (gen_random_uuid(), :b, :alice, 'owner')",
    "invitations": "INSERT INTO invitations (id, workspace_id, role, token_hash, expires_at) "
    "VALUES (gen_random_uuid(), :b, 'member', 'h', now() + interval '1 day')",
    "items": "INSERT INTO items (id, workspace_id, title, is_active) "
    "VALUES (gen_random_uuid(), :b, 't', true)",
}
UPDATES = {
    "workspaces": "UPDATE workspaces SET name = 'hijacked' WHERE id = :b",
    "memberships": "UPDATE memberships SET role = 'admin' WHERE workspace_id = :b",
    "invitations": "UPDATE invitations SET role = 'admin' WHERE workspace_id = :b",
    "items": "UPDATE items SET title = 'hijacked' WHERE workspace_id = :b",
}
DELETES = {
    "workspaces": "DELETE FROM workspaces WHERE id = :b",
    "memberships": "DELETE FROM memberships WHERE workspace_id = :b",
    "invitations": "DELETE FROM invitations WHERE workspace_id = :b",
    "items": "DELETE FROM items WHERE workspace_id = :b",
}
# Settings that must never grant access to workspace B's rows. Alice belongs to A only.
SETTINGS = {
    "foreign workspace": lambda s: {"user": s.alice.id, "workspace": s.b.id},
    "foreign workspace, no user": lambda s: {"workspace": s.b.id},
    "no settings": lambda s: {},
    "user only": lambda s: {"user": s.alice.id},
    "workspace only": lambda s: {"workspace": s.a.id},
    "empty strings": lambda s: {"user": "", "workspace": ""},
}


async def run(engine, seed, setting, statement):
    connection = await scoped(engine, **SETTINGS[setting](seed))
    try:
        result = await connection.execute(
            text(statement),
            {"a": seed.a.id, "b": seed.b.id, "alice": seed.alice.id, "bob": seed.bob.id},
        )
        return result.rowcount if result.returns_rows is False else len(result.all())
    finally:
        await connection.close()


@pytest.mark.parametrize("setting", SETTINGS)
@pytest.mark.parametrize("table", READS)
async def test_b_rows_are_invisible_without_a_matching_user_and_workspace(
    test_db_engine, seeded, table, setting
):
    assert (
        await run(test_db_engine, seeded, setting, f"SELECT 1 FROM {table} WHERE {READS[table]}")
        == 0
    )


@pytest.mark.parametrize("setting", SETTINGS)
@pytest.mark.parametrize("table", UPDATES)
async def test_b_rows_cannot_be_updated_or_deleted(test_db_engine, seeded, table, setting):
    assert await run(test_db_engine, seeded, setting, UPDATES[table]) == 0
    assert await run(test_db_engine, seeded, setting, DELETES[table]) == 0


@pytest.mark.parametrize("setting", SETTINGS)
@pytest.mark.parametrize("name", INSERTS)
async def test_rows_cannot_be_inserted_into_b(test_db_engine, seeded, name, setting):
    with pytest.raises(DBAPIError, match="row-level security"):
        await run(test_db_engine, seeded, setting, INSERTS[name])


async def test_nothing_of_b_survived_the_attempts(owner_engine, seeded, test_db_engine):
    for setting in SETTINGS:
        for statement in (*UPDATES.values(), *DELETES.values()):
            await run(test_db_engine, seeded, setting, statement)
    async with owner_engine.connect() as connection:
        counts = [
            await connection.scalar(
                text(f"SELECT count(*) FROM {t} WHERE {READS[t]}"), {"b": seeded.b.id}
            )
            for t in READS
        ]
        name = await connection.scalar(
            text("SELECT name FROM workspaces WHERE id = :b"), {"b": seeded.b.id}
        )
    assert counts == [1, 1, 1, 1] and name == "B"


@pytest.mark.parametrize(
    "bad", [{"user": "not-a-uuid"}, {"user": "x", "workspace": "y"}, {"workspace": "not-a-uuid"}]
)
@pytest.mark.parametrize("table", READS)
async def test_malformed_settings_fail_closed(test_db_engine, seeded, table, bad):
    """An error or no rows, never rows."""
    connection = await scoped(test_db_engine, **bad)
    try:
        try:
            rows = (await connection.execute(text(f"SELECT 1 FROM {table}"))).all()
        except DBAPIError:
            return
        assert rows == []
    finally:
        await connection.close()


async def test_a_member_still_has_access_to_their_own_workspace(test_db_engine, seeded):
    own = {"user": seeded.alice.id, "workspace": seeded.a.id}
    connection = await scoped(test_db_engine, **own)
    try:
        for table, where in (
            ("items", "workspace_id = :a"),
            ("workspaces", "id = :a"),
            ("memberships", "workspace_id = :a"),
        ):
            rows = await connection.execute(
                text(f"SELECT 1 FROM {table} WHERE {where}"), {"a": seeded.a.id}
            )
            assert len(rows.all()) == 1, table
    finally:
        await connection.close()
