"""Tests for AuthService."""
import pytest
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.user import UserRepository
from app.schemas.user import UserLogin, UserRegister
from app.services.auth import AuthService


@pytest.fixture
def auth_service(test_db: Session) -> AuthService:
    """Create auth service."""
    user_repo = UserRepository(test_db)
    return AuthService(user_repo)


def test_register_new_user(auth_service: AuthService, test_db: Session):
    """Test registering a new user."""
    data = UserRegister(
        email="newuser@example.com",
        name="New User",
        password="password123",
    )
    user = auth_service.register_with_email(data)

    assert user.email == "newuser@example.com"
    assert user.name == "New User"
    assert user.is_active is True


def test_register_duplicate_email(auth_service: AuthService, test_user):
    """Test registering with duplicate email."""
    data = UserRegister(
        email=test_user.email,
        name="Another User",
        password="password123",
    )
    with pytest.raises(HTTPException) as exc_info:
        auth_service.register_with_email(data)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_authenticate_success(auth_service: AuthService, test_user):
    """Test successful authentication."""
    data = UserLogin(
        email=test_user.email,
        password="testpassword123",
    )
    user = auth_service.authenticate_with_email(data)

    assert user.email == test_user.email
    assert user.is_active is True


def test_authenticate_invalid_email(auth_service: AuthService):
    """Test authentication with invalid email."""
    data = UserLogin(
        email="nonexistent@example.com",
        password="password123",
    )
    with pytest.raises(HTTPException) as exc_info:
        auth_service.authenticate_with_email(data)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_authenticate_invalid_password(auth_service: AuthService, test_user):
    """Test authentication with invalid password."""
    data = UserLogin(
        email=test_user.email,
        password="wrongpassword",
    )
    with pytest.raises(HTTPException) as exc_info:
        auth_service.authenticate_with_email(data)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
