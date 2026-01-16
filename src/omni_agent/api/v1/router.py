"""API v1 router aggregating all v1 endpoints."""

from fastapi import APIRouter

from omni_agent.api.v1.endpoints import agent, health, knowledge, team, tools, trace, acp
from omni_agent.core.config import settings

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(team.router, tags=["team"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(trace.router, prefix="/trace", tags=["trace"])

# ACP (Agent Client Protocol) endpoints
if settings.ENABLE_ACP:
    api_router.include_router(acp.router, tags=["acp"])

# Health endpoint at root level (not versioned)
health_router = APIRouter()
health_router.include_router(health.router, tags=["health"])
