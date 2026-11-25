"""Test requests use the normal async unit of work on isolated Postgres schemas."""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import URL, Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateSchema, DropSchema

from alembic import command
from app.core.config import Settings, postgres_url
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.modules.auth.models import User


@pytest.fixture(scope="session")
def database_url() -> URL:
    raw = os.getenv("DATABASE_URL")
    if not raw:
        pytest.fail("Set DATABASE_URL to a dedicated Postgres test database or run make test.")
    return postgres_url(raw)


def migration_config(connection: Connection) -> Config:
    return Config("alembic.ini", attributes={"connection": connection})


@pytest.fixture
async def empty_db_engine(database_url: URL) -> AsyncIterator[AsyncEngine]:
    admin = create_async_engine(
        database_url, poolclass=NullPool, connect_args={"connect_timeout": 3}
    )
    schema = f"test_{uuid4().hex}"
    try:
        async with admin.begin() as connection:
            await connection.execute(CreateSchema(schema))
        engine = create_async_engine(
            database_url,
            poolclass=NullPool,
            connect_args={"options": f"-csearch_path={schema}", "connect_timeout": 3},
        )
        try:
            yield engine
        finally:
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.execute(DropSchema(schema, cascade=True))
    finally:
        await admin.dispose()


@pytest.fixture
async def test_db_engine(empty_db_engine: AsyncEngine) -> AsyncEngine:
    # Concurrent index operations require Alembic to manage its own transactions.
    async with empty_db_engine.connect() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
    return empty_db_engine


@pytest.fixture
def session_factory(test_db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(test_db_engine, expire_on_commit=False)


@pytest.fixture
async def test_db(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def config(database_url: URL) -> Settings:
    return Settings(
        env="test",
        database_url=database_url.render_as_string(hide_password=False),
        secret_key=os.environ["SECRET_KEY"],
        _env_file=None,
    )


@pytest.fixture
def app(config, session_factory):
    return create_app(config, session_factory)


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        yield client


@pytest.fixture(scope="session")
def test_password_hash() -> str:
    return hash_password("testpassword123")


@pytest.fixture
async def test_user(session_factory, test_password_hash: str) -> User:
    async with session_factory.begin() as session:
        user = User(
            email="test@example.com",
            name="Test User",
            hashed_password=test_password_hash,
            is_active=True,
        )
        session.add(user)
    return user


@pytest.fixture
def auth_headers(test_user: User, config: Settings) -> dict[str, str]:
    token = create_access_token({"sub": str(test_user.id)}, config)
    return {"Authorization": f"Bearer {token}"}
