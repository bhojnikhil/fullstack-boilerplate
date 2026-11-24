"""Tests for items router."""
from fastapi.testclient import TestClient


def test_create_item(client: TestClient, auth_headers: dict[str, str]):
    """Test creating an item."""
    response = client.post(
        "/items",
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


def test_get_items(client: TestClient, auth_headers: dict[str, str]):
    """Test getting items."""
    # Create an item first
    client.post(
        "/items",
        headers=auth_headers,
        json={
            "title": "Test Item",
            "description": "Test Description",
        },
    )

    # Get items
    response = client.get("/items", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["title"] == "Test Item"


def test_create_item_unauthorized(client: TestClient):
    """Test creating item without auth."""
    response = client.post(
        "/items",
        json={
            "title": "Test Item",
            "description": "Test Description",
        },
    )

    assert response.status_code == 403
