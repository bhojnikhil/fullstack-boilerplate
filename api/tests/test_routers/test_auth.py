"""Tests for auth router."""
from fastapi.testclient import TestClient
from app.models.user import User


def test_register(client: TestClient):
    """Test user registration."""
    response = client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "name": "New User",
            "password": "password123",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["name"] == "New User"


def test_register_duplicate_email(client: TestClient, test_user: User):
    """Test registration with duplicate email."""
    response = client.post(
        "/auth/register",
        json={
            "email": test_user.email,
            "name": "Another User",
            "password": "password123",
        },
    )

    assert response.status_code == 400


def test_login(client: TestClient, test_user: User):
    """Test user login."""
    response = client.post(
        "/auth/login",
        json={
            "email": test_user.email,
            "password": "testpassword123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client: TestClient):
    """Test login with invalid credentials."""
    response = client.post(
        "/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "wrongpassword",
        },
    )

    assert response.status_code == 401


def test_get_current_user(client: TestClient, auth_headers: dict[str, str]):
    """Test getting current user."""
    response = client.get("/auth/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "email" in data


def test_get_current_user_unauthorized(client: TestClient):
    """Test getting current user without auth."""
    response = client.get("/auth/me")

    assert response.status_code == 403
