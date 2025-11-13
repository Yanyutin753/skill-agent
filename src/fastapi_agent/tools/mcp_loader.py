"""MCP tool loader with official MCP Python SDK integration.

This module implements MCP (Model Context Protocol) client integration based on
the official modelcontextprotocol/python-sdk.

Supports multiple transports:
- stdio: Local process communication (e.g., npx, python, uv)
- sse: Server-Sent Events (HTTP streaming)
- http: Streamable HTTP (bidirectional HTTP)

Official SDK documentation: https://github.com/modelcontextprotocol/python-sdk
"""

import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

from .base import Tool, ToolResult

# Type alias for transport types
TransportType = Literal["stdio", "sse", "http"]


class MCPTool(Tool):
    """Wrapper for MCP tools from official SDK.

    This class wraps tools provided by MCP servers and adapts them to our
    Tool interface. It handles communication with the MCP server via the
    ClientSession.

    The tool execution follows official SDK patterns:
    - Calls session.call_tool() with tool name and arguments
    - Handles CallToolResult with content and structuredContent
    - Converts MCP TextContent to our ToolResult format
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        session: ClientSession,
    ):
        """Initialize MCPTool with tool metadata and session.

        Args:
            name: Tool name from MCP server
            description: Tool description
            parameters: Tool input schema (JSON Schema)
            session: Active MCP ClientSession for calling tools
        """
        self._name = name
        self._description = description
        self._parameters = parameters
        self._session = session

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs) -> ToolResult:
        """Execute MCP tool via the session.

        This follows the official SDK pattern:
        1. Call session.call_tool(name, arguments)
        2. Get CallToolResult with content list
        3. Extract TextContent from result.content
        4. Check result.isError for error status

        Args:
            **kwargs: Tool arguments matching the input schema

        Returns:
            ToolResult with success status and content
        """
        try:
            # Call MCP tool using official SDK ClientSession
            result = await self._session.call_tool(self._name, arguments=kwargs)

            # Extract content from CallToolResult
            # result.content is a list of content items (TextContent, ImageContent, etc.)
            content_parts = []
            for item in result.content:
                # Check if item has text attribute (TextContent)
                if hasattr(item, 'text'):
                    content_parts.append(item.text)
                else:
                    # Fallback for other content types
                    content_parts.append(str(item))

            content_str = '\n'.join(content_parts)

            # Check for error status (official SDK: result.isError)
            is_error = result.isError if hasattr(result, 'isError') else False

            return ToolResult(
                success=not is_error,
                content=content_str,
                error=None if not is_error else "Tool returned error"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"MCP tool execution failed: {str(e)}"
            )


class MCPServerConnection:
    """Manages connection to a single MCP server using official SDK.

    This class handles the lifecycle of an MCP server connection:
    - Establishes stdio/SSE/HTTP connection to MCP server
    - Initializes ClientSession following official SDK patterns
    - Lists and wraps available tools
    - Manages cleanup on disconnect

    Supports multiple transports:
    - stdio: For local processes (npx, python, uv)
    - sse: For Server-Sent Events endpoints
    - http: For Streamable HTTP endpoints

    Official SDK Reference:
    https://github.com/modelcontextprotocol/python-sdk/blob/main/README.md
    """

    def __init__(
        self,
        name: str,
        transport: TransportType = "stdio",
        # stdio parameters
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        # http/sse parameters
        url: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        """Initialize MCP server connection parameters.

        Args:
            name: Server name for identification
            transport: Transport type ('stdio', 'sse', or 'http')
            command: Command to start the MCP server (stdio only)
            args: Arguments for the command (stdio only)
            env: Environment variables for the server process (stdio only)
            url: Server URL (sse/http only)
            headers: HTTP headers (sse/http only)
        """
        self.name = name
        self.transport = transport
        # stdio parameters
        self.command = command
        self.args = args or []
        self.env = env or {}
        # http/sse parameters
        self.url = url
        self.headers = headers or {}
        # connection state
        self.session: ClientSession | None = None
        self.exit_stack: AsyncExitStack | None = None
        self.tools: list[MCPTool] = []

    async def connect(self) -> bool:
        """Connect to the MCP server using official SDK patterns.

        This follows the official SDK connection pattern for different transports:

        **stdio transport**:
        1. Create StdioServerParameters with command, args, env
        2. Use stdio_client() as async context manager
        3. Create ClientSession with read/write streams

        **sse transport**:
        1. Use sse_client(url, headers) as async context manager
        2. Create ClientSession with read/write streams

        **http transport**:
        1. Use streamablehttp_client(url, headers) as async context manager
        2. Create ClientSession with read/write/session_id streams

        Then for all transports:
        4. Initialize the session
        5. List available tools

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Use AsyncExitStack to manage multiple async context managers
            self.exit_stack = AsyncExitStack()

            # Create appropriate client based on transport type
            if self.transport == "stdio":
                # stdio transport (official SDK pattern)
                if not self.command:
                    raise ValueError(f"Server '{self.name}': command required for stdio transport")

                server_params = StdioServerParameters(
                    command=self.command,
                    args=self.args,
                    env=self.env if self.env else None
                )

                # Enter stdio client context
                read_stream, write_stream = await self.exit_stack.enter_async_context(
                    stdio_client(server_params)
                )

            elif self.transport == "sse":
                # SSE transport (official SDK pattern)
                if not self.url:
                    raise ValueError(f"Server '{self.name}': url required for sse transport")

                # Enter SSE client context
                read_stream, write_stream = await self.exit_stack.enter_async_context(
                    sse_client(url=self.url, headers=self.headers)
                )

            elif self.transport == "http":
                # HTTP transport (official SDK pattern)
                if not self.url:
                    raise ValueError(f"Server '{self.name}': url required for http transport")

                # Enter streamable HTTP client context
                # Note: streamablehttp_client returns (read, write, session_id)
                result = await self.exit_stack.enter_async_context(
                    streamablehttp_client(url=self.url, headers=self.headers)
                )

                # Unpack result (may have 2 or 3 elements depending on SDK version)
                if len(result) == 3:
                    read_stream, write_stream, _session_id = result
                else:
                    read_stream, write_stream = result

            else:
                raise ValueError(f"Unsupported transport type: {self.transport}")

            # Enter client session context (same for all transports)
            session = await self.exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            self.session = session

            # Initialize the session
            await session.initialize()

            # List available tools
            tools_list = await session.list_tools()

            # Wrap each tool
            for tool in tools_list.tools:
                parameters = tool.inputSchema if hasattr(tool, 'inputSchema') else {}

                mcp_tool = MCPTool(
                    name=tool.name,
                    description=tool.description or "",
                    parameters=parameters,
                    session=session
                )
                self.tools.append(mcp_tool)

            print(f"✓ Connected to MCP server '{self.name}' ({self.transport}) - loaded {len(self.tools)} tools")
            for tool in self.tools:
                desc = tool.description[:60] if len(tool.description) > 60 else tool.description
                print(f"  - {tool.name}: {desc}...")
            return True

        except Exception as e:
            print(f"✗ Failed to connect to MCP server '{self.name}': {e}")
            # Clean up exit stack if connection failed
            if self.exit_stack:
                await self.exit_stack.aclose()
                self.exit_stack = None
            import traceback
            traceback.print_exc()
            return False

    async def disconnect(self):
        """Properly disconnect from the MCP server.

        Cleanup follows official SDK pattern using AsyncExitStack.
        """
        if self.exit_stack:
            # AsyncExitStack handles all cleanup properly
            await self.exit_stack.aclose()
            self.exit_stack = None
            self.session = None


# Global connections registry
_mcp_connections: list[MCPServerConnection] = []


async def load_mcp_tools_async(config_path: str = "mcp.json") -> list[Tool]:
    """Load MCP tools from config file using official SDK.

    This function implements the MCP client pattern from official SDK:
    1. Read mcp.json config file
    2. Parse mcpServers configuration
    3. Connect to each enabled server via stdio/sse/http
    4. Fetch tool definitions from each server
    5. Wrap tools in our Tool interface

    Config file format supports multiple transports:

    **stdio transport** (local process):
    ```json
    {
      "mcpServers": {
        "server_name": {
          "command": "python",
          "args": ["server.py"],
          "env": {"API_KEY": "value"},
          "disabled": false
        }
      }
    }
    ```

    **http/sse transport** (remote endpoint):
    ```json
    {
      "mcpServers": {
        "server_name": {
          "type": "http",
          "url": "https://mcp.example.com/mcp",
          "headers": {"Authorization": "Bearer token"},
          "disabled": false
        }
      }
    }
    ```

    Args:
        config_path: Path to MCP configuration file (default: "mcp.json")

    Returns:
        List of Tool objects representing MCP tools

    Example:
        ```python
        tools = await load_mcp_tools_async("mcp.json")
        for tool in tools:
            print(f"Loaded: {tool.name}")
        ```
    """
    global _mcp_connections

    config_file = Path(config_path)

    if not config_file.exists():
        print(f"ℹ️  MCP config not found: {config_path} (skipping MCP tools)")
        return []

    try:
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        # Official SDK config format: mcpServers
        mcp_servers = config.get("mcpServers", {})

        if not mcp_servers:
            print("ℹ️  No MCP servers configured")
            return []

        all_tools = []

        # Connect to each enabled server
        for server_name, server_config in mcp_servers.items():
            # Skip disabled servers
            if server_config.get("disabled", False):
                print(f"⊘ Skipping disabled server: {server_name}")
                continue

            # Determine transport type
            transport = server_config.get("type", "stdio").lower()

            # Validate transport type
            if transport not in ["stdio", "sse", "http"]:
                print(f"⚠️  Unknown transport '{transport}' for server '{server_name}', skipping")
                continue

            # Create connection based on transport type
            if transport == "stdio":
                # stdio transport: requires command
                command = server_config.get("command")
                args = server_config.get("args", [])
                env = server_config.get("env", {})

                if not command:
                    print(f"⚠️  No command specified for stdio server: {server_name}")
                    continue

                connection = MCPServerConnection(
                    name=server_name,
                    transport="stdio",
                    command=command,
                    args=args,
                    env=env,
                )

            else:  # sse or http
                # http/sse transport: requires url
                url = server_config.get("url")
                headers = server_config.get("headers", {})

                if not url:
                    print(f"⚠️  No url specified for {transport} server: {server_name}")
                    continue

                connection = MCPServerConnection(
                    name=server_name,
                    transport=transport,  # type: ignore
                    url=url,
                    headers=headers,
                )

            # Connect to server
            success = await connection.connect()

            if success:
                _mcp_connections.append(connection)
                all_tools.extend(connection.tools)

        print(f"\n✅ Total MCP tools loaded: {len(all_tools)}")

        return all_tools

    except Exception as e:
        print(f"❌ Error loading MCP config: {e}")
        import traceback
        traceback.print_exc()
        return []


async def cleanup_mcp_connections():
    """Clean up all MCP connections.

    This should be called on application shutdown to properly close
    all MCP server connections.

    Example:
        ```python
        # In FastAPI lifespan
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            yield
            # Shutdown
            await cleanup_mcp_connections()
        ```
    """
    global _mcp_connections
    for connection in _mcp_connections:
        await connection.disconnect()
    _mcp_connections.clear()
    print("🧹 All MCP connections cleaned up")
