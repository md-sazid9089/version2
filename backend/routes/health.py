"""
Health Check Route
===================
Provides a simple GET /health endpoint that returns a minimal status
payload for uptime checks and basic connectivity tests.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Return the canonical health payload."""
    return {"status": "ok"}
