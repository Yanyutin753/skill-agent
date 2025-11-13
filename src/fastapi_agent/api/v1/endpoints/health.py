"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@router.get("/")
async def root() -> dict[str, str | dict[str, str]]:
    """Root endpoint with API information."""
    return {
        "name": "FastAPI Agent",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "agent": "/api/v1/agent/run",
            "tools": "/api/v1/tools",
            "docs": "/docs",
        },
    }
