"""Omni Agent CLI module.

This module provides an interactive command-line interface for Omni Agent.

Usage:
    omni-agent [OPTIONS]

Example:
    omni-agent --workspace /path/to/project
"""

from omni_agent.cli.commands import AVAILABLE_COMMANDS
from omni_agent.cli.display import Colors
from omni_agent.cli.main import main

__all__ = ["main", "Colors", "AVAILABLE_COMMANDS"]
