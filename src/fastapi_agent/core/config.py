"""Application configuration using pydantic-settings."""

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Project metadata
    PROJECT_NAME: str = "FastAPI Agent"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "AI Agent with tool execution capabilities via FastAPI"
    DEBUG: bool = False

    # API settings
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = Field(
        default_factory=lambda: ["*"]
    )

    # LLM settings (supports 100+ providers via LiteLLM)
    # Model naming: "provider/model" e.g. "openai/gpt-4o", "anthropic/claude-3-5-sonnet-20241022"
    # For custom endpoints: set LLM_API_BASE and use "openai/model-name" format
    LLM_API_KEY: str = Field(default="", description="API key for LLM service")
    LLM_API_BASE: str = Field(
        default="",
        description="Optional custom API base URL (leave empty for default provider endpoints)"
    )
    LLM_MODEL: str = Field(
        default="anthropic/claude-3-5-sonnet-20241022",
        description="Model name in format 'provider/model' e.g. openai/gpt-4o, anthropic/claude-3-5-sonnet-20241022"
    )

    # Agent settings
    AGENT_MAX_STEPS: int = Field(default=50, ge=1, le=200)
    AGENT_WORKSPACE_DIR: str = Field(default="./workspace")

    # Skills settings
    ENABLE_SKILLS: bool = Field(default=True, description="Enable Claude Skills support")
    SKILLS_DIR: str = Field(default="src/fastapi_agent/skills", description="Skills directory path")

    # MCP (Model Context Protocol) settings
    ENABLE_MCP: bool = Field(default=True, description="Enable MCP tool integration")
    MCP_CONFIG_PATH: str = Field(
        default="mcp.json",
        description="Path to MCP configuration file"
    )

    # RAG / Knowledge Base settings
    ENABLE_RAG: bool = Field(default=True, description="Enable RAG knowledge base")
    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port")
    POSTGRES_USER: str = Field(default="postgres", description="PostgreSQL user")
    POSTGRES_PASSWORD: str = Field(default="", description="PostgreSQL password")
    POSTGRES_DB: str = Field(default="knowledge_base", description="PostgreSQL database name")

    # DashScope Embedding settings
    DASHSCOPE_API_KEY: str = Field(default="", description="DashScope API key for embeddings")
    DASHSCOPE_API_BASE: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="DashScope API base URL"
    )
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-v4",
        description="Embedding model name"
    )
    EMBEDDING_DIMENSION: int = Field(
        default=1024,
        description="Embedding vector dimension"
    )

    # RAG Chunking settings
    CHUNK_SIZE: int = Field(default=500, description="Text chunk size in characters")
    CHUNK_OVERLAP: int = Field(default=50, description="Overlap between chunks")
    RAG_TOP_K: int = Field(default=5, description="Number of results to return in RAG search")

    # Session management settings
    ENABLE_SESSION: bool = Field(default=True, description="Enable session management")
    SESSION_BACKEND: str = Field(
        default="file",
        description="Session storage backend: 'file', 'redis', or 'postgres'"
    )
    SESSION_STORAGE_PATH: str = Field(
        default="~/.fastapi-agent/sessions.json",
        description="Path to session storage file (for file backend)"
    )
    SESSION_MAX_AGE_DAYS: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Maximum age of sessions in days before cleanup"
    )
    SESSION_MAX_RUNS_PER_SESSION: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum number of runs to keep per session"
    )
    SESSION_HISTORY_RUNS: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Number of recent runs to include in history context"
    )

    # Redis session settings (when SESSION_BACKEND=redis)
    SESSION_REDIS_HOST: str = Field(default="localhost", description="Redis host")
    SESSION_REDIS_PORT: int = Field(default=6379, description="Redis port")
    SESSION_REDIS_DB: int = Field(default=0, description="Redis database number")
    SESSION_REDIS_PASSWORD: str = Field(default="", description="Redis password")

    # PostgreSQL session settings (when SESSION_BACKEND=postgres)
    # Uses POSTGRES_* settings from RAG configuration
    SESSION_POSTGRES_TABLE: str = Field(
        default="agent_sessions",
        description="PostgreSQL table name for sessions"
    )

    # Run log settings
    ENABLE_DEBUG_LOGGING: bool = Field(
        default=False,
        description="Enable debug logging to files (when False, only console output)"
    )
    RUN_LOG_BACKEND: str = Field(
        default="file",
        description="Run log storage backend: 'file' or 'redis'"
    )
    RUN_LOG_DIR: str = Field(
        default="./logs",
        description="Directory for run log files (for file backend)"
    )
    RUN_LOG_RETENTION_DAYS: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Number of days to retain run logs"
    )
    RUN_LOG_REDIS_PREFIX: str = Field(
        default="agent_run:",
        description="Redis key prefix for run logs"
    )
    RUN_LOG_REDIS_TTL: int = Field(
        default=86400 * 7,
        description="TTL for run logs in Redis (seconds, default 7 days)"
    )

    @property
    def postgres_dsn(self) -> str:
        """Build PostgreSQL connection string."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Spawn Agent settings
    ENABLE_SPAWN_AGENT: bool = Field(
        default=True,
        description="Enable spawn_agent tool for sub-agent creation"
    )
    SPAWN_AGENT_MAX_DEPTH: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum nesting depth for spawned agents"
    )
    SPAWN_AGENT_DEFAULT_MAX_STEPS: int = Field(
        default=15,
        ge=5,
        le=30,
        description="Default max steps for spawned sub-agents"
    )
    SPAWN_AGENT_TOKEN_LIMIT: int = Field(
        default=50000,
        ge=10000,
        le=100000,
        description="Token limit for spawned sub-agents"
    )

    # System prompt
    SYSTEM_PROMPT: str = Field(
        default="""你是一个功能强大的 AI 助手。

## 核心能力
- **文件操作**：读取、编写、编辑各类文件
- **编程辅助**：编写代码、调试、执行命令
- **数据处理**：处理和分析各种格式的数据
- **网络功能**：网络搜索、获取在线信息

## 知识库
你可以访问包含用户上传文档的知识库。回答问题时，请先使用 `search_knowledge` 工具搜索相关信息。

## 工具选择规则（重要）
1. **旅游/出行相关**：当用户询问旅游攻略、景点推荐、路线规划、天气查询、美食住宿时，**必须**使用高德地图工具（maps_*），不要使用网络搜索
2. **编程/技术问题**：使用网络搜索获取最新文档和解决方案
3. **通用问题**：根据问题类型选择合适的工具

## 子任务委派策略
当需要委派复杂任务给子agent时，请遵循以下流程：

1. **评估任务**：判断任务是否需要专业领域知识
2. **加载技能**：如果需要，先使用 `get_skill` 加载相关skill的完整内容
3. **委派执行**：使用 `spawn_agent` 创建子agent，将skill内容作为context传递

示例流程：
```
用户请求: "帮我做安全审计"
步骤1: get_skill("security-audit") -> 获取安全审计专业指导
步骤2: spawn_agent(
    task="审计src/auth模块的安全性",
    role="security auditor",
    context=<skill内容>,
    tools=["read_file", "bash"]
)
```

这样子agent将获得专业领域知识指导，提高任务完成质量。

## 工作方式
- 先分析用户需求，选择正确的工具
- 清晰解释操作步骤
- 使用专业工具获取准确信息

{SKILLS_METADATA}"""
    )

    @field_validator("LLM_MODEL")
    @classmethod
    def validate_model_format(cls, v: str) -> str:
        """Standardize model name format to 'provider/model'.

        Supports:
        - Standard format: "anthropic/claude-3-5-sonnet-20241022"
        - Legacy colon format: "openai:gpt-4o" -> "openai/gpt-4o"
        - No prefix format: "claude-3-5-sonnet-20241022" -> auto-detect provider
        """
        if not v or not v.strip():
            raise ValueError("LLM_MODEL cannot be empty")

        v = v.strip()

        # Convert colon to slash (legacy format)
        if ":" in v and "/" not in v:
            v = v.replace(":", "/")

        # If already has provider prefix, return as-is
        if "/" in v:
            return v

        # Auto-detect provider based on model name
        model_lower = v.lower()

        # Provider detection rules
        if "claude" in model_lower:
            return f"anthropic/{v}"
        elif "gpt" in model_lower or v.startswith("o1") or v.startswith("o3"):
            return f"openai/{v}"
        elif "gemini" in model_lower:
            return f"gemini/{v}"
        elif "mistral" in model_lower:
            return f"mistral/{v}"
        elif "llama" in model_lower:
            return f"together_ai/{v}"
        elif "qwen" in model_lower or "deepseek" in model_lower:
            # Chinese models, often used with custom API base
            return f"openai/{v}"
        else:
            # Default to openai for unknown models (custom endpoints)
            return f"openai/{v}"

    @field_validator("AGENT_WORKSPACE_DIR")
    @classmethod
    def validate_workspace_dir(cls, v: str) -> str:
        """Ensure workspace directory exists."""
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return str(path.absolute())

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


# Global settings instance
settings = Settings()
