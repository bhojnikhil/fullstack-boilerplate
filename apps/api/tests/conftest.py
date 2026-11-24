"""Pytest configuration and shared fixtures."""

import os
from collections.abc import Generator
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateSchema, DropSchema

from alembic import command
from app.auth.security import hash_password
from app.core.db import get_db
from app.main import app
from app.models.user import User


@pytest.fixture(scope="session")
def database_url():
    raw = os.getenv("DATABASE_URL")
    if not raw:
        pytest.fail("Set DATABASE_URL to a dedicated Postgres test database or run make test.")
    url = make_url(raw)
    if url.drivername not in ("postgresql", "postgresql+psycopg"):
        pytest.fail("DATABASE_URL must use Postgres with psycopg 3.")
    return url.set(drivername="postgresql+psycopg")


@pytest.fixture
def test_db_engine(database_url):
    """Use a fresh, migrated Postgres schema for every database test."""
    admin = create_engine(database_url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    schema = f"test_{uuid4().hex}"
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(
        database_url,
        poolclass=NullPool,
        connect_args={"options": f"-csearch_path={schema}", "connect_timeout": 3},
    )
    try:
        with engine.begin() as connection:
            alembic = Config("alembic.ini", attributes={"connection": connection})
            command.upgrade(alembic, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


@pytest.fixture
def test_db(test_db_engine) -> Generator[Session]:
    with sessionmaker(test_db_engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def client(test_db: Session) -> Generator[TestClient]:
    """Create test client with test database."""

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def test_user(test_db: Session) -> User:
    """Create test user."""
    user = User(
        email="test@example.com",
        name="Test User",
        hashed_password=hash_password("testpassword123"),
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client: TestClient, test_user: User) -> dict[str, str]:
    """Get authorization headers for test user."""
    response = client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "testpassword123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
