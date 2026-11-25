"""Revision 0003: auth tables, case-insensitive emails, dropping stored Google tokens."""

from io import StringIO
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from tests.conftest import migration_config


async def migrate(engine, action, revision: str) -> None:
    async with engine.connect() as connection:
        await connection.run_sync(lambda conn: action(migration_config(conn), revision))


async def oauth_columns(engine) -> set[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'oauth_accounts'"
            )
        )
        return {row[0] for row in rows}


async def test_0003_drops_stored_google_tokens_but_keeps_links(empty_db_engine):
    await migrate(empty_db_engine, command.upgrade, "0002")
    user_id = uuid4()
    async with empty_db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, email, name, is_active) VALUES (:id, 'g@x.com', 'G', true)"
            ),
            {"id": user_id},
        )
        await connection.execute(
            text(
                "INSERT INTO oauth_accounts (id, user_id, provider, provider_account_id, "
                "access_token, refresh_token) VALUES (:id, :user, 'google', 'sub-1', "
                "'plaintext-access', 'plaintext-refresh')"
            ),
            {"id": uuid4(), "user": user_id},
        )

    await migrate(empty_db_engine, command.upgrade, "head")
    async with empty_db_engine.connect() as connection:
        await connection.run_sync(lambda conn: command.check(migration_config(conn)))
        link = (await connection.execute(text("SELECT * FROM oauth_accounts"))).mappings().one()
        verified = await connection.scalar(text("SELECT email_verified_at FROM users"))
    assert link["provider_account_id"] == "sub-1"
    assert "plaintext" not in str(dict(link))
    assert verified is None  # Existing users start unverified.
    assert not {"access_token", "refresh_token", "expires_at"} & await oauth_columns(
        empty_db_engine
    )

    await migrate(empty_db_engine, command.downgrade, "0002")
    assert {"access_token", "refresh_token", "expires_at"} <= await oauth_columns(empty_db_engine)
    async with empty_db_engine.connect() as connection:
        restored = await connection.scalar(text("SELECT access_token FROM oauth_accounts"))
    assert restored == ""  # The tokens are gone for good.
    await migrate(empty_db_engine, command.upgrade, "head")


async def test_0003_refuses_emails_that_differ_only_by_case(empty_db_engine):
    await migrate(empty_db_engine, command.upgrade, "0002")
    async with empty_db_engine.begin() as connection:
        for email in ("Dup@Example.com", "dup@example.com"):
            await connection.execute(
                text(
                    "INSERT INTO users (id, email, name, is_active) VALUES (:id, :email, 'D', true)"
                ),
                {"id": uuid4(), "email": email},
            )
    with pytest.raises(RuntimeError, match="differ only|letter case"):
        await migrate(empty_db_engine, command.upgrade, "head")
    async with empty_db_engine.begin() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
        await connection.execute(text("DELETE FROM users WHERE email = 'Dup@Example.com'"))
    await migrate(empty_db_engine, command.upgrade, "head")


async def test_0003_retries_after_an_interrupted_concurrent_index_build(empty_db_engine):
    await migrate(empty_db_engine, command.upgrade, "0002")
    async with empty_db_engine.begin() as connection:
        # As if the concurrent build ran but the revision was never recorded.
        await connection.execute(
            text("CREATE UNIQUE INDEX ux_users_email_lower ON users (lower(email))")
        )
    await migrate(empty_db_engine, command.upgrade, "head")
    async with empty_db_engine.connect() as connection:
        await connection.run_sync(lambda conn: command.check(migration_config(conn)))


def test_0003_offline_sql_builds_the_index_concurrently():
    output = StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=output), "0002:0003", sql=True)
    statements = output.getvalue()
    before, after = statements.split("CREATE UNIQUE INDEX CONCURRENTLY ux_users_email_lower", 1)
    assert before.rfind("COMMIT;") > before.rfind("BEGIN;")
    assert "ALTER TABLE oauth_accounts DROP COLUMN access_token" in after
    assert "CREATE TABLE auth_sessions" in after
