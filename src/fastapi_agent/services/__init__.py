"""Services module for FastAPI Agent."""

from fastapi_agent.services.desktop_controller import (
    DesktopController,
    get_desktop_controller,
)

__all__ = [
    "DesktopController",
    "get_desktop_controller",
]
