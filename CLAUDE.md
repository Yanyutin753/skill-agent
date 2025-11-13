# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses **uv** as the package manager (faster than pip) and **Make** for common tasks.

### Essential Commands
```bash
# Install dependencies
make install        # or: uv sync

# Development server (with hot reload)
make dev            # or: uv run uvicorn fastapi_agent.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
make test           # or: uv run pytest -v
make test-cov       # Run tests with coverage

# Code quality
make lint           # Check code with ruff
make lint-fix       # Auto-fix linting issues
make format         # Format code with ruff
make check          # Run all checks (lint, format, type)

# Single test file
uv run pytest tests/core/test_agent.py -v

# Specific test function
uv run pytest tests/core/test_agent.py::test_function_name -v
```

### Important Notes
- **Always use `uv run`** instead of direct `python` when running scripts
- The project uses **Python 3.11+** (required)
- Source code is in `src/fastapi_agent/`, not root level

## Architecture Overview

### Core Components

**1. Agent Execution Loop** (`src/fastapi_agent/core/agent.py`)
- Manages the complete AI agent lifecycle
- Integrates TokenManager for context management (prevents overflow at 120k tokens)
- Integrates AgentLogger for structured JSON logging
- Executes multi-step tasks with tool calls until completion or max_steps reached

**2. Token Management** (`src/fastapi_agent/core/token_manager.py`)
- Uses tiktoken (cl100k_base) for precise token counting
- Automatically summarizes message history when exceeding token_limit
- Summarization strategy: keeps all user messages, compresses agent execution rounds
- Can reduce token usage by 50-70% while preserving context

**3. Structured Logging** (`src/fastapi_agent/core/agent_logger.py`)
- Creates timestamped log files: `~/.fastapi-agent/log/agent_run_YYYYMMDD_HHMMSS.log`
- Logs: STEP (token usage), REQUEST, RESPONSE, TOOL_EXECUTION (with timing), COMPLETION
- Critical for debugging agent behavior and performance analysis

**4. MCP Integration** (`src/fastapi_agent/services/mcp_manager.py`, `src/fastapi_agent/tools/mcp_loader.py`)
- Loads external tools via Model Context Protocol at startup
- Configuration in `mcp.json` (supports stdio, SSE, HTTP transports)
- Tools stored globally in `api/deps.py` and injected into agent
- **Important**: MCP tools must be loaded during FastAPI lifespan startup, not per-request

### Request Flow

```
HTTP Request → FastAPI Router (api/v1/agent.py)
            ↓
    Dependency Injection (api/deps.py)
    - get_llm_client()
    - get_tools() [includes MCP + base + skills]
            ↓
    Agent.run() (core/agent.py)
    - TokenManager checks/summarizes
    - AgentLogger records each step
    - LLM generates response
    - Tools execute (with timing)
    - Loop until complete or max_steps
            ↓
    Return response with execution_logs
```

### Tool System

**Tool Loading Priority** (in `api/deps.py:get_tools()`):
1. Base tools: ReadTool, WriteTool, EditTool, BashTool
2. MCP tools: Loaded at startup via `initialize_mcp_tools()`
3. Skills: Dynamically loaded via SkillTool

**Adding New Tools**:
1. Create tool class inheriting from `Tool` base class (`tools/base.py`)
2. Implement: `name`, `description`, `parameters`, `execute()` method
3. Register in `api/deps.py:get_tools()` function
4. Tools are automatically exposed in OpenAPI schema

### Configuration System

Uses **pydantic-settings** with `.env` file support (`core/config.py`):

**Critical Settings**:
- `ENABLE_MCP=true`: Must be true for MCP tools to load
- `ENABLE_SKILLS=true`: Must be true for Skills system
- `MCP_CONFIG_PATH=mcp.json`: Path to MCP configuration
- `LLM_API_KEY`: Required for LLM calls
- `AGENT_MAX_STEPS=50`: Prevents infinite loops
- Token management is always enabled (120k default limit)

**Environment Variables vs Config**:
- `.env` is primary configuration source
- Settings are validated and processed in `Settings` class
- Access via global `settings` instance

### Skills System

**Location**: `src/fastapi_agent/skills/` (internal) and `./skills/` (external)

**Architecture**:
- Each skill is a directory with `SKILL.md` file
- `SkillTool` (`skills/skill_tool.py`) loads skills on-demand via `get_skill` tool
- Skills provide expert guidance (not executable code)
- System prompt automatically includes skill metadata when `ENABLE_SKILLS=true`

**Skill Structure**:
```
skills/my-skill/
├── SKILL.md          # Main skill content (loaded by get_skill tool)
└── reference/        # Optional supporting docs
```

### MCP Configuration

**File**: `mcp.json` (JSON schema: https://modelcontextprotocol.io/schema/mcp.json)

**Structure**:
```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",              // or python, node, etc.
      "args": ["-y", "package-name"],
      "env": {"API_KEY": "value"},   // Environment variables for server
      "disabled": false              // Set true to disable without removing
    }
  }
}
```

**Common Issue**: If MCP tools don't load:
1. Check `ENABLE_MCP=true` in `.env`
2. Verify `mcp.json` exists and is valid JSON
3. Check startup logs for MCP initialization messages
4. Debug logs written to `/tmp/mcp_init_debug.log`

## Testing Strategy

**Test Structure**:
- `tests/api/` - API endpoint tests
- `tests/core/` - Core component tests (agent, llm_client, token_manager)
- `tests/tools/` - Tool execution tests
- `tests/services/` - Service layer tests

**Running Tests**:
```bash
# All tests
make test

# With coverage
make test-cov

# Specific module
uv run pytest tests/core/test_agent.py -v

# With output
uv run pytest tests/core/ -v -s
```

## Project Constraints

**IMPORTANT PATHS**:
- Source code: `src/fastapi_agent/` (NOT `fastapi_agent/`)
- Tests: `tests/`
- External skills: `./skills/`
- Workspace: `./workspace/` (agent file operations default here)
- Logs: `~/.fastapi-agent/log/` (agent execution logs)

**Python Import Paths**:
- Always import as: `from fastapi_agent.core import Agent`
- Never: `from src.fastapi_agent.core import Agent`
- The `src/` is in the Python path via `pyproject.toml` configuration

**Critical Implementation Details**:
1. **MCP Loading**: Must happen in FastAPI lifespan startup, not per-request
2. **Token Management**: Automatic, but can be configured via Agent constructor
3. **Logging**: Automatic for all agent runs when `enable_logging=True` (default)
4. **Tools**: Base tools + MCP tools + Skills all merged in `get_tools()`
5. **PYTHONPATH**: When running from src/, must rename old `fastapi_agent/` to avoid conflicts

## API Endpoints

**Base URL**: `http://localhost:8000`

**Key Endpoints**:
- `POST /api/v1/agent/run` - Execute agent with task
- `GET /api/v1/tools/` - List all available tools
- `GET /health` - Health check
- `GET /docs` - OpenAPI/Swagger documentation

**Agent Request Format**:
```json
{
  "message": "Task description",
  "workspace_dir": "./workspace",  // optional
  "max_steps": 50                  // optional
}
```

**Response includes**:
- `success`: boolean
- `message`: final agent response
- `steps`: number of steps taken
- `logs`: array of execution logs with token usage and timing

## Common Pitfalls

1. **Old Directory Conflicts**: If `fastapi_agent/` exists at root, rename it (should only be `src/fastapi_agent/`)
2. **MCP Not Loading**: Check `ENABLE_MCP=true` and verify `initialize_mcp_tools()` is called in lifespan
3. **Import Errors**: Use `uv run` prefix, ensure `PYTHONPATH` includes `src/` if running directly
4. **Token Overflow**: Already handled automatically by TokenManager, but configurable via `token_limit` parameter
5. **Missing Logs**: Check `~/.fastapi-agent/log/` directory, ensure `enable_logging=True` in Agent constructor

## Documentation

- `README.md` - Complete user guide with examples
- `IMPLEMENTATION_SUMMARY.md` - Detailed implementation notes for Token management, AgentLogger, MCP
- `QUICKSTART.md` - Quick setup guide
- API docs available at `/docs` when server is running
