"""Tests for items router."""

from httpx import AsyncClient


async def test_create_item(client: AsyncClient, auth_headers: dict[str, str]):
    """Test creating an item."""
    response = await client.post(
        "/v1/items",
        headers=auth_headers,
        json={
            "title": "Test Item",
            "description": "Test Description",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Item"
    assert data["description"] == "Test Description"


async def test_get_items(client: AsyncClient, auth_headers: dict[str, str]):
    """Test getting items."""
    # Create an item first
    await client.post(
        "/v1/items",
        headers=auth_headers,
        json={
            "title": "Test Item",
            "description": "Test Description",
        },
    )

    # Get items
    response = await client.get("/v1/items", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["items"]
    assert len(data) >= 1
    assert data[0]["title"] == "Test Item"


async def test_create_item_unauthorized(client: AsyncClient):
    """Test creating item without auth."""
    response = await client.post(
        "/v1/items",
        json={
            "title": "Test Item",
            "description": "Test Description",
        },
    )

    # Missing credentials: 401 + WWW-Authenticate (older FastAPI returned 403).
    assert response.status_code == 401
