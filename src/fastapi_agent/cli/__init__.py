"""FastAPI Agent CLI module.

This module provides an interactive command-line interface for FastAPI Agent.

Usage:
    fastapi-agent [OPTIONS]

Example:
    fastapi-agent --workspace /path/to/project
"""

from fastapi_agent.cli.commands import AVAILABLE_COMMANDS
from fastapi_agent.cli.display import Colors
from fastapi_agent.cli.main import main

__all__ = ["main", "Colors", "AVAILABLE_COMMANDS"]
