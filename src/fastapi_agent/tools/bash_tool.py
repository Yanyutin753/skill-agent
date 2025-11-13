"""Bash command execution tool."""

import asyncio
import subprocess
from typing import Any
from .base import Tool, ToolResult


class BashTool(Tool):
    """Execute bash commands."""

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute bash commands in the shell. Use for system operations, "
            "file management, running scripts, etc. Returns stdout and stderr."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str, timeout: int = 30) -> ToolResult:
        """Execute bash command."""
        try:
            # Run command with timeout
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Command timed out after {timeout} seconds",
                )

            # Decode output
            stdout_text = stdout.decode("utf-8") if stdout else ""
            stderr_text = stderr.decode("utf-8") if stderr else ""

            # Combine output
            output = ""
            if stdout_text:
                output += stdout_text
            if stderr_text:
                if output:
                    output += "\n"
                output += f"STDERR:\n{stderr_text}"

            # Check return code
            if process.returncode != 0:
                return ToolResult(
                    success=False,
                    content=output,
                    error=f"Command failed with exit code {process.returncode}",
                )

            return ToolResult(success=True, content=output or "Command executed successfully")
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))
