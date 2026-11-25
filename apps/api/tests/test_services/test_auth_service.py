"""Tests for AuthService."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.modules.auth.repository import UserRepository
from app.modules.auth.schemas import UserLogin, UserRegister
from app.modules.auth.service import AuthService


@pytest.fixture
def auth_service(test_db: AsyncSession, config: Settings) -> AuthService:
    """Create auth service."""
    user_repo = UserRepository(test_db)
    return AuthService(user_repo, config)


async def test_register_new_user(auth_service: AuthService, test_db: AsyncSession):
    """Test registering a new user."""
    data = UserRegister(
        email="newuser@example.com",
        name="New User",
        password="password123",
    )
    user = await auth_service.register_with_email(data)

    assert user.email == "newuser@example.com"
    assert user.name == "New User"
    assert user.is_active is True


async def test_register_duplicate_email(auth_service: AuthService, test_user):
    """Test registering with duplicate email."""
    data = UserRegister(
        email=test_user.email,
        name="Another User",
        password="password123",
    )
    with pytest.raises(DomainError) as exc_info:
        await auth_service.register_with_email(data)

    assert exc_info.value.code == ErrorCode.EMAIL_CONFLICT


async def test_authenticate_success(auth_service: AuthService, test_user):
    """Test successful authentication."""
    data = UserLogin(
        email=test_user.email,
        password="testpassword123",
    )
    user = await auth_service.authenticate_with_email(data)

    assert user.email == test_user.email
    assert user.is_active is True


async def test_authenticate_invalid_email(auth_service: AuthService):
    """Test authentication with invalid email."""
    data = UserLogin(
        email="nonexistent@example.com",
        password="password123",
    )
    with pytest.raises(DomainError) as exc_info:
        await auth_service.authenticate_with_email(data)

    assert exc_info.value.code == ErrorCode.INVALID_CREDENTIALS


async def test_authenticate_invalid_password(auth_service: AuthService, test_user):
    """Test authentication with invalid password."""
    data = UserLogin(
        email=test_user.email,
        password="wrongpassword",
    )
    with pytest.raises(DomainError) as exc_info:
        await auth_service.authenticate_with_email(data)

    assert exc_info.value.code == ErrorCode.INVALID_CREDENTIALS
