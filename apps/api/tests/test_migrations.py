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
        for email in ("Dup@example.com", "dup@example.com"):
            await connection.execute(
                text(
                    "INSERT INTO users (id, email, name, is_active) VALUES (:id, :email, 'D', true)"
                ),
                {"id": uuid4(), "email": email},
            )
    # A failed concurrent build leaves an INVALID index behind, as an interrupted one can.
    async with empty_db_engine.connect() as connection:
        await connection.execution_options(isolation_level="AUTOCOMMIT")
        with pytest.raises(Exception, match="duplicate|unique"):
            await connection.execute(
                text(
                    "CREATE UNIQUE INDEX CONCURRENTLY ux_users_email_lower ON users (lower(email))"
                )
            )
    async with empty_db_engine.begin() as connection:
        valid = await connection.scalar(
            text(
                "SELECT indisvalid FROM pg_index WHERE indexrelid = 'ux_users_email_lower'::regclass"
            )
        )
        assert valid is False
        await connection.execute(text("DELETE FROM users WHERE email = 'Dup@example.com'"))
    await migrate(empty_db_engine, command.upgrade, "head")
    async with empty_db_engine.connect() as connection:
        await connection.run_sync(lambda conn: command.check(migration_config(conn)))
        valid = await connection.scalar(
            text(
                "SELECT indisvalid FROM pg_index WHERE indexrelid = 'ux_users_email_lower'::regclass"
            )
        )
    assert valid is True


async def test_0003_refuses_duplicate_identities_before_any_ddl(empty_db_engine):
    await migrate(empty_db_engine, command.upgrade, "0002")
    user_id = uuid4()
    async with empty_db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, email, name, is_active) VALUES (:id, 'u@x.com', 'U', true)"
            ),
            {"id": user_id},
        )
        for subject in ("first", "second"):
            await connection.execute(
                text(
                    "INSERT INTO oauth_accounts (id, user_id, provider, provider_account_id, "
                    "access_token) VALUES (:id, :user, 'google', :subject, '')"
                ),
                {"id": uuid4(), "user": user_id, "subject": subject},
            )
    with pytest.raises(RuntimeError, match="more than one linked identity"):
        await migrate(empty_db_engine, command.upgrade, "head")
    async with empty_db_engine.connect() as connection:
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
        # Nothing was built, including the concurrent index that runs first.
        assert await connection.scalar(text("SELECT to_regclass('ux_users_email_lower')")) is None


def test_0003_offline_sql_builds_the_index_concurrently():
    output = StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=output), "0002:0003", sql=True)
    statements = output.getvalue()
    before, after = statements.split("CREATE UNIQUE INDEX CONCURRENTLY ux_users_email_lower", 1)
    assert before.rfind("COMMIT;") > before.rfind("BEGIN;")
    assert "ALTER TABLE oauth_accounts DROP COLUMN access_token" in after
    assert "CREATE TABLE auth_sessions" in after


async def test_0003_disarms_links_from_the_old_email_matching(
    empty_db_engine, config, google, test_password_hash
):
    """Pre-hijacked legacy data: an attacker registered the address with a password and
    the old flow linked the owner's Google identity to that account (B4)."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.factory import create_app

    await migrate(empty_db_engine, command.upgrade, "0002")
    hijacked, google_only = uuid4(), uuid4()
    async with empty_db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, is_active) VALUES "
                "(:hijacked, 'victim@gmail.com', 'Attacker', :hash, true), "
                "(:google_only, 'person@gmail.com', 'Person', NULL, true)"
            ),
            {"hijacked": hijacked, "google_only": google_only, "hash": test_password_hash},
        )
        await connection.execute(
            text(
                "INSERT INTO oauth_accounts (id, user_id, provider, provider_account_id, "
                "access_token) VALUES (:a, :hijacked, 'google', 'victim-sub', 'x'), "
                "(:b, :google_only, 'google', 'person-sub', 'y')"
            ),
            {"a": uuid4(), "b": uuid4(), "hijacked": hijacked, "google_only": google_only},
        )
    await migrate(empty_db_engine, command.upgrade, "head")
    async with empty_db_engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT provider_account_id, state FROM oauth_accounts")
        )
        states = {subject: state for subject, state in rows}  # noqa: C416
    assert states == {"victim-sub": "unconfirmed", "person-sub": "linked"}

    app = create_app(config, async_sessionmaker(empty_db_engine, expire_on_commit=False))
    app.state.google_verifier = google
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        # The attacker's password no longer works (the address was never proven).
        attacker = await client.post(
            "/v1/auth/login", json={"email": "victim@gmail.com", "password": "testpassword123"}
        )
        assert attacker.status_code == 401
        # The owner's Google sign-in proves the inbox: the account is claimed for them.
        victim = await client.post(
            "/v1/auth/google",
            json={"id_token": google.issue(subject="victim-sub", email="victim@gmail.com")},
        )
        assert victim.status_code == 200
        assert victim.json()["user"]["sign_in_methods"] == ["google"]
        # A legacy account created by Google itself keeps working.
        person = await client.post(
            "/v1/auth/google",
            json={"id_token": google.issue(subject="person-sub", email="person@gmail.com")},
        )
        assert person.status_code == 200
    async with empty_db_engine.connect() as connection:
        password = await connection.scalar(
            text("SELECT hashed_password FROM users WHERE id = :id"), {"id": hijacked}
        )
    assert password is None
