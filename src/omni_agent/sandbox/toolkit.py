"""Sandbox toolkit - creates all sandbox tools for a session."""

from typing import Optional

from omni_agent.tools.base import Tool
from omni_agent.sandbox.manager import SandboxManager, SandboxInstance
from omni_agent.sandbox.tools import (
    SandboxShellTool,
    SandboxReadTool,
    SandboxWriteTool,
    SandboxEditTool,
    SandboxJupyterTool,
    SandboxListDirTool,
)


class SandboxToolkit:
    """Factory for creating sandbox-isolated tools.

    Creates a complete set of tools that execute in an isolated
    sandbox environment, one sandbox per session.

    Usage:
        manager = SandboxManager(base_url="http://localhost:8080")
        await manager.initialize()

        toolkit = SandboxToolkit(manager)
        tools = await toolkit.get_tools("session-123")

        # tools contains: bash, read_file, write_file, edit_file, python, list_dir
    """

    def __init__(
        self,
        sandbox_manager: SandboxManager,
        enable_shell: bool = True,
        enable_file_ops: bool = True,
        enable_jupyter: bool = True,
    ) -> None:
        self._manager = sandbox_manager
        self._enable_shell = enable_shell
        self._enable_file_ops = enable_file_ops
        self._enable_jupyter = enable_jupyter

    async def get_tools(self, session_id: str) -> list[Tool]:
        """Get all sandbox tools for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of Tool instances bound to the session's sandbox
        """
        sandbox = await self._manager.get_sandbox(session_id)
        return self._create_tools(sandbox)

    def _create_tools(self, sandbox: SandboxInstance) -> list[Tool]:
        """Create tool instances for a sandbox."""
        tools: list[Tool] = []

        if self._enable_shell:
            tools.append(SandboxShellTool(sandbox))

        if self._enable_file_ops:
            tools.extend([
                SandboxReadTool(sandbox),
                SandboxWriteTool(sandbox),
                SandboxEditTool(sandbox),
                SandboxListDirTool(sandbox),
            ])

        if self._enable_jupyter:
            tools.append(SandboxJupyterTool(sandbox))

        return tools

    async def cleanup_session(self, session_id: str) -> bool:
        """Remove sandbox for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if removed, False if not found
        """
        return await self._manager.remove_sandbox(session_id)

    @property
    def manager(self) -> SandboxManager:
        return self._manager
