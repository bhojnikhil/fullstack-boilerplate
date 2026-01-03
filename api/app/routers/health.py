"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """
    Health check endpoint.

    Returns status ok if server is running.
    """
    return {"status": "ok"}
