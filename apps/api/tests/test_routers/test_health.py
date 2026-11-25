"""Tests for health router."""

from httpx import AsyncClient


async def test_health_check(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
