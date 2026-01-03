"""Tests for AuthService."""
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.services.auth import AuthService
from app.repositories.user import UserRepository
from app.auth.security import hash_password, verify_password


@pytest.fixture
def auth_service(test_db: Session) -> AuthService:
    """Create auth service."""
    user_repo = UserRepository(test_db)
    return AuthService(user_repo)


def test_register_new_user(auth_service: AuthService, test_db: Session):
    """Test registering a new user."""
    user = auth_service.register(
        email="newuser@example.com",
        name="New User",
        password="password123",
    )

    assert user.email == "newuser@example.com"
    assert user.name == "New User"
    assert user.is_active is True


def test_register_duplicate_email(auth_service: AuthService, test_user):
    """Test registering with duplicate email."""
    with pytest.raises(HTTPException) as exc_info:
        auth_service.register(
            email=test_user.email,
            name="Another User",
            password="password123",
        )

    assert exc_info.value.status_code == 400


def test_login_success(auth_service: AuthService, test_user):
    """Test successful login."""
    token_data = auth_service.login(
        email=test_user.email,
        password="testpassword123",
    )

    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"


def test_login_invalid_email(auth_service: AuthService):
    """Test login with invalid email."""
    with pytest.raises(HTTPException) as exc_info:
        auth_service.login(
            email="nonexistent@example.com",
            password="password123",
        )

    assert exc_info.value.status_code == 401


def test_login_invalid_password(auth_service: AuthService, test_user):
    """Test login with invalid password."""
    with pytest.raises(HTTPException) as exc_info:
        auth_service.login(
            email=test_user.email,
            password="wrongpassword",
        )

    assert exc_info.value.status_code == 401
