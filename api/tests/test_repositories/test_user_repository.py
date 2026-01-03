"""Tests for UserRepository."""
import pytest
from sqlalchemy.orm import Session
from app.repositories.user import UserRepository
from app.models.user import User
from app.auth.security import hash_password


@pytest.fixture
def user_repo(test_db: Session) -> UserRepository:
    """Create user repository."""
    return UserRepository(test_db)


def test_create_user(user_repo: UserRepository):
    """Test creating a user."""
    user = user_repo.create(
        email="newuser@example.com",
        name="New User",
        hashed_password=hash_password("password123"),
    )

    assert user.email == "newuser@example.com"
    assert user.name == "New User"
    assert user.is_active is True


def test_get_user_by_email(user_repo: UserRepository, test_user: User):
    """Test getting user by email."""
    user = user_repo.get_by_email(test_user.email)

    assert user is not None
    assert user.email == test_user.email
    assert user.name == test_user.name


def test_get_user_by_id(user_repo: UserRepository, test_user: User):
    """Test getting user by ID."""
    user = user_repo.get_by_id(test_user.id)

    assert user is not None
    assert user.id == test_user.id
    assert user.email == test_user.email


def test_get_nonexistent_user(user_repo: UserRepository):
    """Test getting nonexistent user."""
    user = user_repo.get_by_email("nonexistent@example.com")
    assert user is None


def test_update_user(user_repo: UserRepository, test_user: User):
    """Test updating user."""
    from app.schemas.user import UserUpdate

    update_data = UserUpdate(name="Updated Name")
    updated = user_repo.update(user=test_user, name="Updated Name")

    assert updated is not None
    assert updated.name == "Updated Name"
    assert updated.id == test_user.id
