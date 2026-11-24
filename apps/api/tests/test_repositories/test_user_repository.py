"""Tests for UserRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository


@pytest.fixture
def user_repo(test_db: AsyncSession) -> UserRepository:
    """Create user repository."""
    return UserRepository(test_db)


async def test_create_user(user_repo: UserRepository):
    """Test creating a user."""
    user = await user_repo.create(
        email="newuser@example.com",
        name="New User",
        hashed_password=hash_password("password123"),
    )

    assert user.email == "newuser@example.com"
    assert user.name == "New User"
    assert user.is_active is True


async def test_get_user_by_email(user_repo: UserRepository, test_user: User):
    """Test getting user by email."""
    user = await user_repo.get_by_email(test_user.email)

    assert user is not None
    assert user.email == test_user.email
    assert user.name == test_user.name


async def test_get_user_by_id(user_repo: UserRepository, test_user: User):
    """Test getting user by ID."""
    user = await user_repo.get_by_id(test_user.id)

    assert user is not None
    assert user.id == test_user.id
    assert user.email == test_user.email


async def test_get_nonexistent_user(user_repo: UserRepository):
    """Test getting nonexistent user."""
    user = await user_repo.get_by_email("nonexistent@example.com")
    assert user is None


async def test_update_user(user_repo: UserRepository, test_user: User):
    """Test updating user."""
    user = await user_repo.get_by_id(test_user.id)
    assert user is not None
    updated = await user_repo.update(user=user, name="Updated Name")

    assert updated is not None
    assert updated.name == "Updated Name"
    assert updated.id == test_user.id
