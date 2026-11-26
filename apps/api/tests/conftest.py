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
from app.factory import create_app
from app.integrations.google_id_token import GoogleIdentity, GoogleTokenError, identity_from_claims
from app.modules.auth.models import SignInMethod, User
from app.modules.auth.sessions import IssuedTokens, SessionService
from app.modules.workspaces.models import Membership, Workspace, WorkspaceRole

TEST_PASSWORD = "testpassword123"
WEB_ORIGIN = "http://localhost:3000"
GOOGLE_WEB_CLIENT_ID = "web-client.apps.googleusercontent.com"
GOOGLE_ANDROID_CLIENT_ID = "android-client.apps.googleusercontent.com"


@pytest.fixture(scope="session")
def database_url() -> URL:
    """The application's URL: a non-owner role that row-level security applies to."""
    raw = os.getenv("DATABASE_URL")
    if not raw:
        pytest.fail("Set DATABASE_URL to a dedicated Postgres test database or run make test.")
    return postgres_url(raw)


@pytest.fixture(scope="session")
def owner_url(database_url: URL) -> URL:
    """The migration owner's URL. Tests migrate and seed as the owner; requests never do."""
    raw = os.getenv("MIGRATION_DATABASE_URL")
    if not raw:
        pytest.fail(
            "Set MIGRATION_DATABASE_URL to the owner role of the test database "
            "(DATABASE_URL is the app role) or run make test."
        )
    url = postgres_url(raw)
    if url.username == database_url.username:
        pytest.fail("MIGRATION_DATABASE_URL and DATABASE_URL must use different roles.")
    return url


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
async def schema_engines(
    database_url: URL, owner_url: URL
) -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    """An empty schema, as (owner engine, app-role engine). The app role gets its table
    privileges from the migrations, as in a real deployment."""
    admin = create_async_engine(owner_url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    schema = f"test_{uuid4().hex}"
    try:
        async with admin.begin() as connection:
            await connection.execute(CreateSchema(schema))
        options = {"options": f"-csearch_path={schema}", "connect_timeout": 3}
        owner = create_async_engine(owner_url, poolclass=NullPool, connect_args=options)
        app_role = create_async_engine(database_url, poolclass=NullPool, connect_args=options)
        try:
            yield owner, app_role
        finally:
            await app_role.dispose()
            await owner.dispose()
            async with admin.begin() as connection:
                await connection.execute(DropSchema(schema, cascade=True))
    finally:
        await admin.dispose()


@pytest.fixture
def empty_db_engine(schema_engines: tuple[AsyncEngine, AsyncEngine]) -> AsyncEngine:
    """The owner's engine on an empty schema (for migration tests)."""
    return schema_engines[0]


@pytest.fixture
async def owner_engine(
    schema_engines: tuple[AsyncEngine, AsyncEngine],
) -> AsyncEngine:
    """The owner's engine on a migrated schema. Superusers bypass row-level security,
    so use it to seed and inspect, never to exercise the API."""
    owner, _ = schema_engines
    # Concurrent index operations require Alembic to manage its own transactions.
    async with owner.connect() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
    return owner


@pytest.fixture
def test_db_engine(owner_engine: AsyncEngine, schema_engines) -> AsyncEngine:
    """The application's engine (non-owner role) on the migrated schema."""
    return schema_engines[1]


@pytest.fixture
def owner_sessions(owner_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(owner_engine, expire_on_commit=False)


@pytest.fixture
def session_factory(test_db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(test_db_engine, expire_on_commit=False)


@pytest.fixture
async def test_db(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def config(database_url: URL, owner_url: URL, secret_key: str) -> Settings:
    return Settings(
        env="test",
        database_url=database_url.render_as_string(hide_password=False),
        migration_database_url=owner_url.render_as_string(hide_password=False),
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
        # Tests treat example.com as a Google Workspace domain unless told otherwise.
        hosted_domain: str | None = "example.com",
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
                **({"hd": hosted_domain} if hosted_domain else {}),
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


async def create_workspace(
    sessions,
    owner: User,
    *,
    name: str = "Test Workspace",
    slug: str | None = None,
    members: tuple[tuple[User, WorkspaceRole], ...] = (),
) -> Workspace:
    """Insert a workspace as the table owner (which bypasses row-level security)."""
    workspace_id = uuid4()
    async with sessions.begin() as db:
        workspace = Workspace(
            id=workspace_id,
            name=name,
            slug=slug or f"ws-{workspace_id.hex[:16]}",
            currency="USD",
            timezone="UTC",
            owner_id=owner.id,
        )
        db.add(workspace)
        await db.flush()
        db.add(Membership(workspace_id=workspace_id, user_id=owner.id, role=WorkspaceRole.OWNER))
        for member, role in members:
            db.add(Membership(workspace_id=workspace_id, user_id=member.id, role=role))
    return workspace


def in_workspace(headers: dict[str, str], workspace: Workspace) -> dict[str, str]:
    return {**headers, "X-Workspace-Id": str(workspace.id)}


@pytest.fixture
async def workspace(owner_sessions, test_user: User) -> Workspace:
    """A workspace owned by ``test_user``."""
    return await create_workspace(owner_sessions, test_user)


@pytest.fixture
def ws_headers(auth_headers: dict[str, str], workspace: Workspace) -> dict[str, str]:
    """``test_user``'s credentials with their workspace active."""
    return in_workspace(auth_headers, workspace)


async def person(
    session_factory, config: Settings, email: str, *, verified: bool = True
) -> tuple[User, dict[str, str]]:
    """A user with a live session: (user, bearer headers)."""
    user = await create_user(
        session_factory, email=email, name=email.split("@")[0], verified=verified
    )
    return user, bearer(await sign_in(session_factory, config, user))


async def owner_query(owner_engine, sql: str, **params):
    """Rows from a read-only statement run as the owner (bypasses row-level security)."""
    from sqlalchemy import text

    async with owner_engine.connect() as connection:
        return (await connection.execute(text(sql), params)).all()
