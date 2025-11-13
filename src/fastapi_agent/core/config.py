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
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8000"]
    )

    # LLM settings
    LLM_API_KEY: str = Field(default="", description="API key for LLM service")
    LLM_API_BASE: str = Field(
        default="https://api.anthropic.com",
        description="Base URL for LLM API"
    )
    LLM_MODEL: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Model name to use"
    )

    # Agent settings
    AGENT_MAX_STEPS: int = Field(default=50, ge=1, le=200)
    AGENT_WORKSPACE_DIR: str = Field(default="./workspace")

    # Skills settings
    ENABLE_SKILLS: bool = Field(default=True, description="Enable Claude Skills support")
    SKILLS_DIR: str = Field(default="./skills", description="Skills directory path")

    # MCP (Model Context Protocol) settings
    ENABLE_MCP: bool = Field(default=True, description="Enable MCP tool integration")
    MCP_CONFIG_PATH: str = Field(
        default="mcp.json",
        description="Path to MCP configuration file"
    )

    # System prompt
    SYSTEM_PROMPT: str = Field(
        default=(
            "You are a helpful AI assistant with access to tools. "
            "Use the available tools to complete tasks efficiently and accurately. "
            "Always provide clear explanations of your actions.\n\n"
            "{SKILLS_METADATA}"
        )
    )

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
