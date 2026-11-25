"""Tests for the auth repositories against Postgres."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository


@pytest.fixture
def user_repo(test_db: AsyncSession) -> UserRepository:
    return UserRepository(test_db)


async def test_create_and_get_user(user_repo: UserRepository):
    user = await user_repo.create("new@example.com", "New User", hashed_password="hash")
    assert user is not None
    assert user.email == "new@example.com"
    assert user.is_active is True
    assert user.email_verified is False
    assert user.created_at is not None
    assert await user_repo.get_by_id(user.id) is user


async def test_create_returns_none_for_any_case_of_an_existing_email(
    user_repo: UserRepository, test_user: User
):
    assert await user_repo.create("TEST@Example.com", "Someone Else") is None


async def test_lookup_ignores_case_including_legacy_rows(user_repo: UserRepository, test_db):
    # Earlier releases stored emails as typed; lookups must still find them.
    await test_db.execute(
        text(
            "INSERT INTO users (id, email, name, is_active) "
            "VALUES (gen_random_uuid(), 'Legacy.Case@Example.com', 'Legacy', true)"
        )
    )
    found = await user_repo.get_by_email("legacy.case@example.com")
    assert found is not None
    assert found.email == "Legacy.Case@Example.com"
    assert await user_repo.get_by_email("nobody@example.com") is None


async def test_verified_flag(user_repo: UserRepository):
    user = await user_repo.create(
        "verified@example.com", "Verified", email_verified_at=datetime.now(UTC)
    )
    assert user is not None
    assert user.email_verified is True
