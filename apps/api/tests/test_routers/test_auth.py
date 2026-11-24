"""Tests for auth router."""

from httpx import AsyncClient

from app.modules.auth.models import User


async def test_register(client: AsyncClient):
    """Test user registration."""
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "name": "New User",
            "password": "password123",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["name"] == "New User"


async def test_register_duplicate_email(client: AsyncClient, test_user: User):
    """Test registration with duplicate email."""
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": test_user.email,
            "name": "Another User",
            "password": "password123",
        },
    )

    assert response.status_code == 409


async def test_login(client: AsyncClient, test_user: User):
    """Test user login."""
    response = await client.post(
        "/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "testpassword123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == test_user.email


async def test_login_invalid_credentials(client: AsyncClient):
    """Test login with invalid credentials."""
    response = await client.post(
        "/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "wrongpassword",
        },
    )

    assert response.status_code == 401


async def test_get_current_user(client: AsyncClient, auth_headers: dict[str, str]):
    """Test getting current user."""
    response = await client.get("/v1/auth/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "email" in data


async def test_get_current_user_unauthorized(client: AsyncClient):
    """Test getting current user without auth."""
    response = await client.get("/v1/auth/me")

    # Missing credentials: 401 + WWW-Authenticate (older FastAPI returned 403).
    assert response.status_code == 401


async def test_password_login_for_inactive_or_google_only_user(client, test_user, session_factory):
    async with session_factory.begin() as session:
        user = await session.merge(test_user)
        user.is_active = False
    credentials = {"email": test_user.email, "password": "testpassword123"}
    response = await client.post("/v1/auth/login", json=credentials)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "inactive_user"

    async with session_factory.begin() as session:
        user = await session.merge(test_user)
        user.is_active = True
        user.hashed_password = None
    response = await client.post("/v1/auth/login", json=credentials)
    assert response.status_code == 401
    assert "Please sign in with Google" in response.json()["error"]["message"]
