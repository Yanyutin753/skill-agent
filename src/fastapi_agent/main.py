"""FastAPI application for Agent API with best practices architecture."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from fastapi_agent.api.deps import cleanup_mcp_tools, initialize_mcp_tools
from fastapi_agent.api.v1.router import api_router, health_router
from fastapi_agent.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    print("=" * 50)
    print("FastAPI Agent Starting...")
    print("=" * 50)
    print(f"Project: {settings.PROJECT_NAME}")
    print(f"Version: {settings.VERSION}")
    print(f"Debug Mode: {settings.DEBUG}")
    print(f"API Base: {settings.LLM_API_BASE}")
    print(f"Model: {settings.LLM_MODEL}")
    print(f"Max Steps: {settings.AGENT_MAX_STEPS}")
    print(f"Workspace: {settings.AGENT_WORKSPACE_DIR}")
    print(f"Skills Enabled: {settings.ENABLE_SKILLS}")
    print(f"MCP Enabled: {settings.ENABLE_MCP}")
    print("=" * 50)

    # Initialize MCP tools
    await initialize_mcp_tools()

    print("=" * 50)
    print("✅ FastAPI Agent Ready!")
    print("=" * 50)

    yield

    # Shutdown
    print("=" * 50)
    print("FastAPI Agent Shutting Down...")
    print("=" * 50)

    # Cleanup MCP connections
    await cleanup_mcp_tools()

    print("✅ Shutdown complete")


def create_application() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.DESCRIPTION,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # Add GZip compression middleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Add trusted host middleware (only in production)
    if not settings.DEBUG:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["localhost", "127.0.0.1", "*.example.com"],
        )

    # Include routers
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


# Create application instance
app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "fastapi_agent.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
