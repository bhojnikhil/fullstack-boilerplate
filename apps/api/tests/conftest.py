"""Test requests use the normal async unit of work on isolated Postgres schemas."""

import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
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
from app.core.client import ClientInfo, Platform
from app.core.config import Settings, postgres_url
from app.core.security import PASSWORDS
from app.integrations.google_id_token import GoogleIdentity, GoogleTokenError, identity_from_claims
from app.main import create_app
from app.modules.auth.models import SignInMethod, User
from app.modules.auth.sessions import IssuedTokens, SessionService

TEST_PASSWORD = "testpassword123"
WEB_ORIGIN = "http://localhost:3000"
GOOGLE_WEB_CLIENT_ID = "web-client.apps.googleusercontent.com"
GOOGLE_ANDROID_CLIENT_ID = "android-client.apps.googleusercontent.com"


@pytest.fixture(scope="session")
def database_url() -> URL:
    raw = os.getenv("DATABASE_URL")
    if not raw:
        pytest.fail("Set DATABASE_URL to a dedicated Postgres test database or run make test.")
    return postgres_url(raw)


@pytest.fixture(scope="session")
def secret_key() -> str:
    value = os.getenv("SECRET_KEY")
    if not value:
        pytest.fail(
            "Set SECRET_KEY to a random test secret (openssl rand -hex 32) or run make test."
        )
    return value


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
def config(database_url: URL, secret_key: str) -> Settings:
    return Settings(
        env="test",
        database_url=database_url.render_as_string(hide_password=False),
        secret_key=secret_key,
        # Per-test, in-process backends. The Postgres limiter has its own tests.
        email_backend="memory",
        rate_limit_backend="memory",
        google_auth_enabled=True,
        google_web_client_id=GOOGLE_WEB_CLIENT_ID,
        google_android_client_id=GOOGLE_ANDROID_CLIENT_ID,
        _env_file=None,
    )


class FakeGoogleVerifier:
    """Stands in for GoogleIdTokenVerifier: maps token strings to identities."""

    def __init__(self) -> None:
        self.identities: dict[str, GoogleIdentity | Exception] = {}

    def issue(
        self,
        *,
        subject: str = "google-subject-1",
        email: str = "google.user@example.com",
        email_verified: bool = True,
        name: str | None = "Google User",
        issued_at: datetime | None = None,
    ) -> str:
        token = f"google-id-token-{uuid4().hex}"
        # Parsed by the real claim handling, like a verified token would be.
        self.identities[token] = identity_from_claims(
            {
                "sub": subject,
                "email": email,
                "email_verified": email_verified,
                "name": name,
                "picture": "https://example.com/avatar.png",
                "iat": int((issued_at or datetime.now(UTC)).timestamp()),
            }
        )
        return token

    def fail(self, error: Exception) -> str:
        token = f"google-id-token-{uuid4().hex}"
        self.identities[token] = error
        return token

    async def verify(self, token: str) -> GoogleIdentity:
        result = self.identities.get(token)
        if result is None:
            raise GoogleTokenError
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def google() -> FakeGoogleVerifier:
    return FakeGoogleVerifier()


@pytest.fixture
def app(config, session_factory, google):
    app = create_app(config, session_factory)
    app.state.google_verifier = google
    return app


@pytest.fixture
def outbox(app) -> list:
    return app.state.email_backend.outbox


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        yield client


@pytest.fixture(scope="session")
def test_password_hash() -> str:
    return PASSWORDS.hash(TEST_PASSWORD)


async def create_user(
    session_factory,
    *,
    email: str = "test@example.com",
    name: str = "Test User",
    hashed_password: str | None = None,
    verified: bool = True,
    is_active: bool = True,
) -> User:
    async with session_factory.begin() as session:
        user = User(
            email=email,
            name=name,
            hashed_password=hashed_password,
            is_active=is_active,
            email_verified_at=datetime.now(UTC) if verified else None,
        )
        session.add(user)
    return user


def client_info(platform: Platform = "other", ip: str = "127.0.0.1") -> ClientInfo:
    return ClientInfo(ip_hash=None, user_agent=None, platform=platform, origin=None, ip=ip)


async def sign_in(
    session_factory,
    config: Settings,
    user: User,
    *,
    platform: Platform = "other",
    authenticated_at: datetime | None = None,
) -> IssuedTokens:
    """Start a session through the real session service (as a sign-in would)."""
    async with session_factory.begin() as db:
        service = SessionService(db, config)
        issued = await service.start(user, SignInMethod.PASSWORD, client_info(platform), None)
        if authenticated_at is not None:
            issued.session.authenticated_at = authenticated_at
    return replace(issued)


def bearer(issued: IssuedTokens) -> dict[str, str]:
    return {"Authorization": f"Bearer {issued.access_token}"}


@pytest.fixture
async def test_user(session_factory, test_password_hash: str) -> User:
    return await create_user(session_factory, hashed_password=test_password_hash)


@pytest.fixture
async def test_session(session_factory, config: Settings, test_user: User) -> IssuedTokens:
    return await sign_in(session_factory, config, test_user)


@pytest.fixture
def auth_headers(test_session: IssuedTokens) -> dict[str, str]:
    return bearer(test_session)
