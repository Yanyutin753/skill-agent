"""场景类型与多场景路由配置。"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class SceneType(Enum):
    """支持的任务路由场景类型。"""

    GENERAL = "general"
    CODE_DEVELOPMENT = "code_development"
    INFORMATION_RETRIEVAL = "information_retrieval"
    TRAVEL_PLANNING = "travel_planning"
    DOCUMENT_PROCESSING = "document_processing"
    DATA_ANALYSIS = "data_analysis"
    WEB_RESEARCH = "web_research"


@dataclass
class SceneConfig:
    """特定场景类型的配置。"""

    scene_type: SceneType

    execution_mode: str = "single"
    """执行模式：'single' 为单 Agent，'team' 为团队模式"""

    base_tools_filter: Optional[List[str]] = None
    """启用的基础工具列表（None 表示全部）"""

    mcp_tools_filter: Optional[List[str]] = None
    """启用的 MCP 工具名称列表（None 表示全部）"""

    enable_rag: bool = False
    """启用 RAG 知识库搜索"""

    system_prompt_prefix: Optional[str] = None
    """添加到系统提示的前缀"""

    suggested_skills: Optional[List[str]] = None
    """建议加载的技能列表"""

    max_steps: Optional[int] = None
    """最大执行步数"""

    token_limit: Optional[int] = None
    """上下文管理的 token 限制"""

    priority: int = 0
    """场景选择优先级（数值越高优先级越高）"""

    keywords: List[str] = field(default_factory=list)
    """基于规则匹配的关键词列表"""

    team_config_name: Optional[str] = None
    """团队配置名称（仅用于 execution_mode='team'）"""

    enable_spawn_agent: Optional[bool] = None
    """覆盖此场景的 spawn_agent 设置"""

    tool_preset: Optional[str] = None
    """工具预设名称（minimal/coding/research/travel/full）"""

    tool_groups: Optional[List[str]] = None
    """工具分组名称（file_ops/code_tools/search_tools/...）"""

    def merge_with_user_config(self, user_config: Optional["AgentConfig"]) -> "AgentConfig":
        """合并场景配置与用户配置（用户配置优先）。

        Args:
            user_config: 用户提供的 AgentConfig（可选）

        Returns:
            合并后的 AgentConfig
        """
        from omni_agent.schemas.message import AgentConfig

        merged = AgentConfig()

        if self.tool_preset:
            merged.tool_preset = self.tool_preset
        if self.tool_groups:
            merged.tool_groups = self.tool_groups
        if self.base_tools_filter:
            merged.base_tools_filter = self.base_tools_filter
        if self.mcp_tools_filter:
            merged.mcp_tools_filter = self.mcp_tools_filter
        if self.max_steps:
            merged.max_steps = self.max_steps
        if self.token_limit:
            merged.token_limit = self.token_limit
        if self.enable_rag:
            merged.enable_rag = self.enable_rag
        if self.enable_spawn_agent is not None:
            merged.enable_spawn_agent = self.enable_spawn_agent

        if user_config:
            if user_config.tool_preset is not None:
                merged.tool_preset = user_config.tool_preset
            if user_config.tool_groups is not None:
                merged.tool_groups = user_config.tool_groups
            if user_config.base_tools_filter is not None:
                merged.base_tools_filter = user_config.base_tools_filter
            if user_config.mcp_tools_filter is not None:
                merged.mcp_tools_filter = user_config.mcp_tools_filter
            if user_config.max_steps is not None:
                merged.max_steps = user_config.max_steps
            if user_config.token_limit is not None:
                merged.token_limit = user_config.token_limit
            if user_config.enable_rag is not None:
                merged.enable_rag = user_config.enable_rag
            if user_config.enable_spawn_agent is not None:
                merged.enable_spawn_agent = user_config.enable_spawn_agent
            if user_config.workspace_dir is not None:
                merged.workspace_dir = user_config.workspace_dir
            if user_config.system_prompt is not None:
                merged.system_prompt = user_config.system_prompt
            if user_config.enable_base_tools is not None:
                merged.enable_base_tools = user_config.enable_base_tools
            if user_config.enable_mcp_tools is not None:
                merged.enable_mcp_tools = user_config.enable_mcp_tools
            if user_config.enable_skills is not None:
                merged.enable_skills = user_config.enable_skills
            if user_config.enable_summarization is not None:
                merged.enable_summarization = user_config.enable_summarization
            if user_config.mcp_config_path is not None:
                merged.mcp_config_path = user_config.mcp_config_path
            if user_config.spawn_agent_max_depth is not None:
                merged.spawn_agent_max_depth = user_config.spawn_agent_max_depth

        return merged
