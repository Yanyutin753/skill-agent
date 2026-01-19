"""FastAPI 端点的依赖注入模块.

提供 FastAPI 端点所需的依赖项，包括：
- LLM 客户端
- Agent 工厂
- 工具集合（基础工具 + MCP 工具 + Skills）
- 会话管理器（支持 file/redis/postgres 后端）
- 沙箱管理器

生命周期管理:
    - initialize_mcp_tools(): 应用启动时加载 MCP 工具
    - cleanup_mcp_tools(): 应用关闭时清理 MCP 连接
    - initialize_session_manager(): 应用启动时初始化会话管理器
    - initialize_sandbox_manager(): 应用启动时初始化沙箱管理器
    - cleanup_sandbox_manager(): 应用关闭时清理沙箱

使用示例:
    @router.post("/run")
    async def run(
        llm_client: LLMClient = Depends(get_llm_client),
        agent_factory: AgentFactory = Depends(get_agent_factory),
    ):
        agent = await agent_factory.create_agent(llm_client, config)
        ...
"""
from pathlib import Path
from typing import Annotated, Optional, TYPE_CHECKING

from fastapi import Depends

if TYPE_CHECKING:
    from omni_agent.sandbox.manager import SandboxManager

from omni_agent.core import Agent, LLMClient, settings
from omni_agent.core.config import Settings
from omni_agent.core.session import AgentSessionManager, TeamSessionManager
from omni_agent.core.session_manager import (
    UnifiedAgentSessionManager,
    UnifiedTeamSessionManager,
)
from omni_agent.skills import create_skill_tools
from omni_agent.tools import (
    BashTool,
    EditTool,
    GlobTool,
    GrepTool,
    ListDirTool,
    ReadTool,
    Tool,
    WriteTool,
    SpawnAgentTool,
    GetUserInputTool,
)
from omni_agent.tools.mcp_loader import cleanup_mcp_connections, load_mcp_tools_async
from omni_agent.tools.note_tool import RecallNoteTool, SessionNoteTool
from omni_agent.tools.rag_tool import RAGTool

# ============================================================================
# 全局状态存储
# ============================================================================

# MCP 工具存储（应用启动时加载）
_mcp_tools: list[Tool] = []

# 会话管理器（应用启动时初始化）
# 支持多种存储后端: file（文件）, redis, postgres
_agent_session_manager: Optional[UnifiedAgentSessionManager] = None
_team_session_manager: Optional[UnifiedTeamSessionManager] = None

# 沙箱管理器（ENABLE_SANDBOX=true 时初始化）
# 每个 session 对应一个隔离的沙箱实例
_sandbox_manager: Optional["SandboxManager"] = None


def get_settings() -> Settings:
    """获取应用配置实例."""
    return settings


def get_llm_client(settings: Annotated[Settings, Depends(get_settings)]) -> LLMClient:
    """获取 LLM 客户端实例.

    使用配置中的 API Key、API Base 和模型名称创建 LLM 客户端。
    支持 100+ 种 LLM 提供商（通过 LiteLLM）。
    """
    return LLMClient(
        api_key=settings.LLM_API_KEY,
        api_base=settings.LLM_API_BASE if settings.LLM_API_BASE else None,
        model=settings.LLM_MODEL,
    )


async def initialize_mcp_tools() -> None:
    """应用启动时初始化 MCP 工具.

    在 FastAPI lifespan 启动阶段调用，从配置文件加载 MCP 工具。
    工具存储在全局 _mcp_tools 列表中，供请求处理时使用。

    调试日志写入 /tmp/mcp_init_debug.log，出错时写入 /tmp/mcp_init_error.log。
    """
    global _mcp_tools

    try:
        import sys

        # 强制刷新以确保输出可见
        debug_log = open("/tmp/mcp_init_debug.log", "w")
        debug_log.write("=== MCP Initialization Debug Log ===\n")
        debug_log.write(f"ENABLE_MCP: {settings.ENABLE_MCP}\n")
        debug_log.write(f"MCP_CONFIG_PATH: {settings.MCP_CONFIG_PATH}\n")
        debug_log.flush()

        if not settings.ENABLE_MCP:
            msg = "ℹ️  MCP integration disabled"
            print(msg, flush=True)
            debug_log.write(msg + "\n")
            debug_log.close()
            return

        msg = f"🔌 Loading MCP tools from: {settings.MCP_CONFIG_PATH}"
        print(msg, flush=True)
        debug_log.write(msg + "\n")
        debug_log.flush()

        mcp_tools = await load_mcp_tools_async(settings.MCP_CONFIG_PATH)
        _mcp_tools = mcp_tools

        if mcp_tools:
            msg = f"✅ Loaded {len(mcp_tools)} MCP tools"
            print(msg, flush=True)
            debug_log.write(msg + "\n")
            for tool in mcp_tools:
                tool_msg = f"  - {tool.name}"
                print(tool_msg, flush=True)
                debug_log.write(tool_msg + "\n")
        else:
            msg = "ℹ️  No MCP tools loaded"
            print(msg, flush=True)
            debug_log.write(msg + "\n")

        debug_log.write("=== MCP Initialization Complete ===\n")
        debug_log.close()
    except Exception as e:
        import traceback
        error_msg = f"❌ Error during MCP initialization: {e}\n{traceback.format_exc()}"
        print(error_msg, flush=True)
        with open("/tmp/mcp_init_error.log", "w") as f:
            f.write(error_msg)


async def cleanup_mcp_tools() -> None:
    """应用关闭时清理 MCP 连接.

    在 FastAPI lifespan 关闭阶段调用，正确关闭所有 MCP 服务器连接并释放资源。
    """
    global _mcp_tools

    if not settings.ENABLE_MCP or not _mcp_tools:
        return

    print("🧹 Cleaning up MCP connections...")
    await cleanup_mcp_connections()
    _mcp_tools = []


async def initialize_session_manager() -> None:
    """应用启动时初始化会话管理器.

    在 FastAPI lifespan 启动阶段调用，初始化 Agent 和 Team 会话管理器。

    支持的存储后端:
    - file: JSON 文件存储（默认，适合开发环境）
    - redis: Redis 存储（高性能，适合生产环境）
    - postgres: PostgreSQL 存储（持久化，可查询）

    启动时会自动清理过期会话（根据 SESSION_MAX_AGE_DAYS 配置）。
    """
    global _agent_session_manager, _team_session_manager

    if not settings.ENABLE_SESSION:
        print("ℹ️  Session management disabled")
        return

    backend = settings.SESSION_BACKEND.lower()
    ttl_seconds = settings.SESSION_MAX_AGE_DAYS * 86400

    try:
        if backend == "file":
            # 文件存储
            base_path = Path(settings.SESSION_STORAGE_PATH).expanduser()
            base_dir = base_path.parent
            base_dir.mkdir(parents=True, exist_ok=True)

            _agent_session_manager = UnifiedAgentSessionManager(
                backend="file",
                storage_path=str(base_dir / "agent_sessions.json"),
                ttl_seconds=ttl_seconds,
            )
            _team_session_manager = UnifiedTeamSessionManager(
                backend="file",
                storage_path=str(base_dir / "team_sessions.json"),
                ttl_seconds=ttl_seconds,
            )
            print(f"✅ Session managers initialized (file): {base_dir}")

        elif backend == "redis":
            # Redis 存储
            _agent_session_manager = UnifiedAgentSessionManager(
                backend="redis",
                redis_host=settings.SESSION_REDIS_HOST,
                redis_port=settings.SESSION_REDIS_PORT,
                redis_db=settings.SESSION_REDIS_DB,
                redis_password=settings.SESSION_REDIS_PASSWORD or None,
                ttl_seconds=ttl_seconds,
            )
            _team_session_manager = UnifiedTeamSessionManager(
                backend="redis",
                redis_host=settings.SESSION_REDIS_HOST,
                redis_port=settings.SESSION_REDIS_PORT,
                redis_db=settings.SESSION_REDIS_DB,
                redis_password=settings.SESSION_REDIS_PASSWORD or None,
                ttl_seconds=ttl_seconds,
            )
            print(f"✅ Session managers initialized (redis): {settings.SESSION_REDIS_HOST}:{settings.SESSION_REDIS_PORT}")

        elif backend in ("postgres", "postgresql"):
            # PostgreSQL 存储
            _agent_session_manager = UnifiedAgentSessionManager(
                backend="postgres",
                postgres_dsn=settings.postgres_dsn,
                postgres_table=settings.SESSION_POSTGRES_TABLE,
                ttl_seconds=ttl_seconds,
            )
            _team_session_manager = UnifiedTeamSessionManager(
                backend="postgres",
                postgres_dsn=settings.postgres_dsn,
                postgres_table=settings.SESSION_POSTGRES_TABLE,
                ttl_seconds=ttl_seconds,
            )
            print(f"✅ Session managers initialized (postgres): {settings.POSTGRES_HOST}")

        else:
            raise ValueError(f"Unknown session backend: {backend}")

        # 启动时自动清理过期会话
        agent_sessions = await _agent_session_manager.get_all_sessions()
        team_sessions = await _team_session_manager.get_all_sessions()
        agent_cleaned = await _agent_session_manager.cleanup_old_sessions(
            max_age_days=settings.SESSION_MAX_AGE_DAYS
        )
        team_cleaned = await _team_session_manager.cleanup_old_sessions(
            max_age_days=settings.SESSION_MAX_AGE_DAYS
        )

        print(f"   Agent sessions: {len(agent_sessions)} (cleaned {agent_cleaned} old)")
        print(f"   Team sessions: {len(team_sessions)} (cleaned {team_cleaned} old)")

    except ImportError as e:
        error_msg = f"❌ Session backend '{backend}' requires additional dependencies: {e}"
        print(error_msg)
        print("   Falling back to file storage...")
        # 回退到文件存储
        base_path = Path(settings.SESSION_STORAGE_PATH).expanduser()
        base_dir = base_path.parent
        base_dir.mkdir(parents=True, exist_ok=True)

        _agent_session_manager = UnifiedAgentSessionManager(
            backend="file",
            storage_path=str(base_dir / "agent_sessions.json"),
        )
        _team_session_manager = UnifiedTeamSessionManager(
            backend="file",
            storage_path=str(base_dir / "team_sessions.json"),
        )
        print(f"⚠️  Falling back to file storage: {base_dir}")

    except Exception as e:
        import traceback
        error_msg = f"❌ Error during session manager initialization: {e}"
        print(error_msg)
        print(traceback.format_exc())
        # 创建回退的文件存储会话管理器
        _agent_session_manager = UnifiedAgentSessionManager(backend="file")
        _team_session_manager = UnifiedTeamSessionManager(backend="file")
        print("⚠️  Falling back to default file session storage")


def get_agent_session_manager() -> Optional[UnifiedAgentSessionManager]:
    """获取全局 Agent 会话管理器实例."""
    return _agent_session_manager


def get_session_manager() -> Optional[UnifiedTeamSessionManager]:
    """获取全局 Team 会话管理器实例."""
    return _team_session_manager


async def initialize_sandbox_manager() -> None:
    """应用启动时初始化沙箱管理器.

    在 FastAPI lifespan 启动阶段调用（当 ENABLE_SANDBOX=true 时）。
    创建 SandboxManager 实例，每个 session 对应一个隔离的沙箱。

    沙箱提供安全的代码执行环境，支持 Docker 容器隔离。
    """
    global _sandbox_manager

    if not settings.ENABLE_SANDBOX:
        print("ℹ️  Sandbox integration disabled")
        return

    try:
        from omni_agent.sandbox.manager import SandboxManager

        _sandbox_manager = SandboxManager(
            base_url=settings.SANDBOX_URL,
            auto_start_docker=settings.SANDBOX_AUTO_START,
            docker_image=settings.SANDBOX_DOCKER_IMAGE,
            ttl_seconds=settings.SANDBOX_TTL_SECONDS,
            max_sandboxes=settings.SANDBOX_MAX_INSTANCES,
        )
        await _sandbox_manager.initialize()
        print(f"✅ Sandbox manager initialized: {settings.SANDBOX_URL}")
    except ImportError:
        print("❌ agent-sandbox not installed. Run: uv add agent-sandbox")
        print("⚠️  Sandbox integration disabled")
    except Exception as e:
        import traceback
        print(f"❌ Error during sandbox initialization: {e}")
        print(traceback.format_exc())


async def cleanup_sandbox_manager() -> None:
    """应用关闭时清理沙箱管理器."""
    global _sandbox_manager

    if _sandbox_manager is None:
        return

    print("🧹 Cleaning up sandbox manager...")
    await _sandbox_manager.shutdown()
    _sandbox_manager = None


def get_sandbox_manager() -> Optional["SandboxManager"]:
    """获取全局沙箱管理器实例."""
    return _sandbox_manager


def get_tools(workspace_dir: str | None = None) -> list[Tool]:
    """获取所有可用工具，包括基础工具、MCP 工具和 Skill 工具.

    工具加载优先级:
    1. 基础工具: read_file, write_file, edit_file, list_dir, glob, grep, bash, note tools
    2. Skill 工具: get_skill（ENABLE_SKILLS=true 时）
    3. MCP 工具: 从 mcp.json 加载（ENABLE_MCP=true 时）
    4. RAG 工具: search_knowledge（ENABLE_RAG=true 时）

    Args:
        workspace_dir: 工作空间目录路径，默认使用 settings.AGENT_WORKSPACE_DIR

    Returns:
        所有可用工具的列表
    """
    workspace_path = Path(workspace_dir or settings.AGENT_WORKSPACE_DIR)
    workspace_path.mkdir(parents=True, exist_ok=True)

    # 基础工具（deepagents 风格的文件系统工具）
    tools = [
        ReadTool(workspace_dir=str(workspace_path)),
        WriteTool(workspace_dir=str(workspace_path)),
        EditTool(workspace_dir=str(workspace_path)),
        ListDirTool(workspace_dir=str(workspace_path)),
        GlobTool(workspace_dir=str(workspace_path)),
        GrepTool(workspace_dir=str(workspace_path)),
        BashTool(),
        SessionNoteTool(memory_file=str(workspace_path / ".agent_memory.json")),
        RecallNoteTool(memory_file=str(workspace_path / ".agent_memory.json")),
        GetUserInputTool(),
    ]

    # Skill 工具
    if settings.ENABLE_SKILLS:
        skill_tools, skill_loader = create_skill_tools(settings.SKILLS_DIR)
        if skill_tools:
            tools.extend(skill_tools)

    # MCP 工具（应用启动时已加载到全局变量）
    if settings.ENABLE_MCP and _mcp_tools:
        tools.extend(_mcp_tools)

    # RAG 工具
    if settings.ENABLE_RAG:
        tools.append(RAGTool())

    return tools


def get_agent(
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Agent:
    """获取配置好工具的 Agent 实例.

    [已废弃] 此方法保留用于向后兼容。
    建议使用 AgentFactory.create_agent() 获取动态配置的 Agent。
    """
    # 确定工作空间目录
    workspace_path = Path(settings.AGENT_WORKSPACE_DIR)
    workspace_path.mkdir(parents=True, exist_ok=True)

    # 获取所有工具
    tools = get_tools(str(workspace_path))

    # 加载系统提示词
    system_prompt = settings.SYSTEM_PROMPT

    # 如果启用则注入 Skills 元数据
    if settings.ENABLE_SKILLS:
        _, skill_loader = create_skill_tools(settings.SKILLS_DIR)
        if skill_loader:
            skills_metadata = skill_loader.get_skills_metadata_prompt()
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
    else:
        # 未启用 Skills 时移除占位符
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

    # 创建 Agent
    return Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=tools,
        max_steps=settings.AGENT_MAX_STEPS,
        workspace_dir=str(workspace_path),
    )


class AgentFactory:
    """Agent 工厂，用于创建动态配置的 Agent.

    相比 get_agent()，AgentFactory 提供更灵活的配置能力：
    - 动态工具选择（base_tools_filter, mcp_tools_filter）
    - 会话隔离的工作空间
    - 沙箱集成（可选）
    - SpawnAgent 嵌套控制
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def create_agent(
        self,
        llm_client: LLMClient,
        config: Optional["AgentConfig"] = None,
        session_id: Optional[str] = None,
    ) -> Agent:
        """创建动态配置的 Agent.

        Args:
            llm_client: LLM 客户端实例
            config: Agent 配置（可选），控制工具、token 限制等
            session_id: 会话 ID，用于工作空间隔离和沙箱关联

        Returns:
            配置完成的 Agent 实例
        """
        from omni_agent.schemas.message import AgentConfig
        from omni_agent.core.workspace import get_workspace_manager

        if config is None:
            config = AgentConfig()

        base_workspace = config.workspace_dir or self.settings.AGENT_WORKSPACE_DIR
        max_steps = config.max_steps or self.settings.AGENT_MAX_STEPS
        token_limit = config.token_limit or 120000
        enable_summarization = config.enable_summarization if config.enable_summarization is not None else True

        workspace_manager = get_workspace_manager(base_workspace)
        workspace_path = workspace_manager.get_session_workspace(session_id)

        # 根据配置构建工具列表（传入 session_id 用于沙箱隔离）
        tools = await self._build_tools(config, str(workspace_path), session_id)

        # 如果启用则添加 SpawnAgentTool（必须在其他工具构建完成后进行）
        tools = self._add_spawn_agent_tool(
            tools=tools,
            config=config,
            workspace_dir=str(workspace_path),
            llm_client=llm_client,
            current_depth=0,  # 根 Agent 从深度 0 开始
        )

        # 构建系统提示词
        system_prompt = config.system_prompt or self.settings.SYSTEM_PROMPT

        # 如果启用则注入 Skills 元数据
        enable_skills = config.enable_skills if config.enable_skills is not None else self.settings.ENABLE_SKILLS
        if enable_skills:
            _, skill_loader = create_skill_tools(self.settings.SKILLS_DIR)
            if skill_loader:
                skills_metadata = skill_loader.get_skills_metadata_prompt()
                system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
        else:
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

        # 创建 Agent
        return Agent(
            llm_client=llm_client,
            system_prompt=system_prompt,
            tools=tools,
            max_steps=max_steps,
            workspace_dir=str(workspace_path),
            token_limit=token_limit,
            enable_summarization=enable_summarization,
        )

    async def _build_tools(
        self,
        config: "AgentConfig",
        workspace_dir: str,
        session_id: Optional[str] = None,
    ) -> list[Tool]:
        """根据配置构建工具列表.

        支持的配置选项:
        - enable_base_tools: 是否启用基础工具
        - base_tools_filter: 指定启用哪些基础工具
        - enable_mcp_tools: 是否启用 MCP 工具
        - mcp_tools_filter: 指定启用哪些 MCP 工具
        - enable_skills: 是否启用 Skill 工具
        - enable_rag: 是否启用 RAG 工具

        沙箱模式:
        当 ENABLE_SANDBOX=true 且提供 session_id 时，
        基础工具会替换为沙箱版本（在 Docker 容器中执行）。
        """
        from omni_agent.schemas.message import AgentConfig

        tools = []

        # 检查是否应该使用沙箱
        use_sandbox = (
            self.settings.ENABLE_SANDBOX
            and _sandbox_manager is not None
            and session_id is not None
        )

        # 基础工具 - 如果启用沙箱则使用沙箱工具，否则使用本地工具
        enable_base = config.enable_base_tools if config.enable_base_tools is not None else True
        if enable_base:
            if use_sandbox:
                from omni_agent.sandbox.toolkit import SandboxToolkit
                toolkit = SandboxToolkit(_sandbox_manager)
                sandbox_tools = await toolkit.get_tools(session_id)
                all_base_tools = sandbox_tools + [
                    SessionNoteTool(memory_file=str(Path(workspace_dir) / ".agent_memory.json")),
                    RecallNoteTool(memory_file=str(Path(workspace_dir) / ".agent_memory.json")),
                    GetUserInputTool(),
                ]
            else:
                all_base_tools = [
                    ReadTool(workspace_dir=workspace_dir),
                    WriteTool(workspace_dir=workspace_dir),
                    EditTool(workspace_dir=workspace_dir),
                    ListDirTool(workspace_dir=workspace_dir),
                    GlobTool(workspace_dir=workspace_dir),
                    GrepTool(workspace_dir=workspace_dir),
                    BashTool(),
                    SessionNoteTool(memory_file=str(Path(workspace_dir) / ".agent_memory.json")),
                    RecallNoteTool(memory_file=str(Path(workspace_dir) / ".agent_memory.json")),
                    GetUserInputTool(),
                ]

            # 构建工具名称映射（支持实际名称和短别名）
            base_tools_map = {}
            for tool in all_base_tools:
                base_tools_map[tool.name] = tool
                # 添加短别名以方便使用
                if tool.name == "read_file":
                    base_tools_map["read"] = tool
                elif tool.name == "write_file":
                    base_tools_map["write"] = tool
                elif tool.name == "edit_file":
                    base_tools_map["edit"] = tool

            # 如果请求了特定工具则进行过滤
            if config.base_tools_filter:
                # 工具去重（以防别名和实际名称同时使用）
                seen = set()
                for name in config.base_tools_filter:
                    if name in base_tools_map:
                        tool = base_tools_map[name]
                        if tool.name not in seen:
                            tools.append(tool)
                            seen.add(tool.name)
            else:
                tools.extend(all_base_tools)

        # Skill 工具
        enable_skills = config.enable_skills if config.enable_skills is not None else self.settings.ENABLE_SKILLS
        if enable_skills:
            skill_tools, _ = create_skill_tools(self.settings.SKILLS_DIR)
            if skill_tools:
                tools.extend(skill_tools)

        # MCP 工具
        enable_mcp = config.enable_mcp_tools if config.enable_mcp_tools is not None else self.settings.ENABLE_MCP
        if enable_mcp:
            # 如果提供了自定义 MCP 配置则使用
            if config.mcp_config_path:
                mcp_tools = await load_mcp_tools_async(config.mcp_config_path)
            else:
                # 使用全局 MCP 工具
                mcp_tools = _mcp_tools

            # 如果请求了特定工具则进行过滤
            if config.mcp_tools_filter and mcp_tools:
                tools.extend([
                    tool for tool in mcp_tools
                    if tool.name in config.mcp_tools_filter
                ])
            elif mcp_tools:
                tools.extend(mcp_tools)

        # RAG 工具
        enable_rag = config.enable_rag if config.enable_rag is not None else self.settings.ENABLE_RAG
        if enable_rag:
            tools.append(RAGTool())

        return tools

    def _add_spawn_agent_tool(
        self,
        tools: list[Tool],
        config: "AgentConfig",
        workspace_dir: str,
        llm_client: LLMClient,
        current_depth: int = 0,
    ) -> list[Tool]:
        """添加 SpawnAgentTool 到工具列表（如果启用）.

        SpawnAgent 允许父 Agent 动态创建子 Agent 执行委托任务。
        通过 max_depth 控制嵌套深度，防止无限递归。

        Args:
            tools: 当前工具列表
            config: Agent 配置
            workspace_dir: 工作空间目录
            llm_client: LLM 客户端
            current_depth: 当前嵌套深度（根 Agent 为 0）

        Returns:
            包含 SpawnAgentTool 的工具列表（如果未达到 max_depth）
        """
        enable_spawn = config.enable_spawn_agent if config.enable_spawn_agent is not None else self.settings.ENABLE_SPAWN_AGENT
        if not enable_spawn:
            return tools

        max_depth = config.spawn_agent_max_depth or self.settings.SPAWN_AGENT_MAX_DEPTH

        # 如果已达到最大深度则不添加 spawn_agent
        if current_depth >= max_depth:
            return tools

        # 使用当前工具作为父工具创建 SpawnAgentTool
        parent_tools = {tool.name: tool for tool in tools}

        spawn_tool = SpawnAgentTool(
            llm_client=llm_client,
            parent_tools=parent_tools,
            workspace_dir=workspace_dir,
            current_depth=current_depth,
            max_depth=max_depth,
            default_max_steps=self.settings.SPAWN_AGENT_DEFAULT_MAX_STEPS,
            default_token_limit=self.settings.SPAWN_AGENT_TOKEN_LIMIT,
        )

        tools.append(spawn_tool)
        return tools


def get_agent_factory(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentFactory:
    """获取 Agent 工厂实例."""
    return AgentFactory(settings)


def get_builtin_research_team(
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> "Team":
    """获取内置的 Web 研究团队实例.

    创建一个包含两个专业 Agent 的团队：
    - Web Search Agent: 使用 exa MCP 工具进行搜索
    - Web Spider Agent: 使用 firecrawl MCP 工具抓取网页
    """
    from omni_agent.core.builtin_teams import create_web_research_team

    # 获取所有可用工具（包括 MCP 工具）
    workspace_path = Path(settings.AGENT_WORKSPACE_DIR)
    workspace_path.mkdir(parents=True, exist_ok=True)
    tools = get_tools(str(workspace_path))

    # 创建并返回团队
    return create_web_research_team(
        llm_client=llm_client,
        available_tools=tools,
        workspace_dir=str(workspace_path),
    )

