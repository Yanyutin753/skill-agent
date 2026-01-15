"""
Structured System Prompt Builder

构建结构化的系统提示,支持多层次上下文组织,参考 agno 的实现。
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

from omni_agent.skills.skill_loader import SkillLoader


@dataclass
class SystemPromptConfig:
    """系统提示配置."""

    # ========== 基础信息 ==========
    name: Optional[str] = None
    """Agent 名称"""

    description: Optional[str] = None
    """Agent 描述 - 添加到提示开头"""

    role: Optional[str] = None
    """Agent 角色定义 - 用 <your_role> 标签包裹"""

    # ========== 指令 ==========
    instructions: List[str] = field(default_factory=list)
    """指令列表 - 用 <instructions> 标签包裹"""

    # ========== 输出规范 ==========
    expected_output: Optional[str] = None
    """期望输出格式 - 用 <expected_output> 标签包裹"""

    markdown: bool = False
    """是否要求使用 markdown 格式化输出"""

    # ========== 上下文控制 ==========
    add_datetime_to_context: bool = False
    """是否添加当前时间到上下文"""

    add_workspace_info: bool = True
    """是否添加工作空间信息"""

    timezone: str = "UTC"
    """时区标识符 (例如 'UTC', 'Asia/Shanghai')"""

    # ========== 额外信息 ==========
    additional_context: Optional[str] = None
    """额外上下文 - 添加到提示末尾"""

    additional_information: List[str] = field(default_factory=list)
    """额外信息列表 - 用 <additional_information> 标签包裹"""

    # ========== 动态内容 ==========
    custom_sections: Dict[str, str] = field(default_factory=dict)
    """自定义章节 {标签名: 内容}"""


class SystemPromptBuilder:
    """构建结构化的系统提示."""

    def __init__(self):
        self.sections: List[str] = []

    def build(
        self,
        config: SystemPromptConfig,
        workspace_dir: Optional[Path] = None,
        skill_loader: Optional[SkillLoader] = None,
        tool_instructions: Optional[List[str]] = None,
    ) -> str:
        """构建系统提示.

        Args:
            config: 系统提示配置
            workspace_dir: 工作空间目录
            skill_loader: Skill 加载器(用于注入 skills 元数据)
            tool_instructions: 工具使用说明列表

        Returns:
            构建好的系统提示字符串
        """
        self.sections = []

        # 1. Agent 名称
        if config.name:
            self.sections.append(f"# {config.name}\n")

        # 2. Agent 描述
        if config.description:
            self.sections.append(config.description)

        # 3. 角色定义
        if config.role:
            self.sections.append(self._build_role_section(config.role))

        # 4. 指令列表
        if config.instructions:
            self.sections.append(self._build_instructions_section(config.instructions))

        # 5. Markdown 格式化说明
        if config.markdown:
            self.sections.append(self._build_markdown_section())

        # 6. 工具使用说明
        if tool_instructions:
            self.sections.append(self._build_tool_instructions_section(tool_instructions))

        # 7. Skills 元数据 (Progressive Disclosure Level 1)
        if skill_loader:
            skills_metadata = skill_loader.get_skills_metadata_prompt()
            if skills_metadata:
                self.sections.append(skills_metadata)

        # 8. 期望输出格式
        if config.expected_output:
            self.sections.append(self._build_expected_output_section(config.expected_output))

        # 9. 工作空间信息
        if config.add_workspace_info and workspace_dir:
            self.sections.append(self._build_workspace_section(workspace_dir))

        # 10. 时间信息
        if config.add_datetime_to_context:
            self.sections.append(self._build_datetime_section(config.timezone))

        # 11. 额外信息列表
        if config.additional_information:
            self.sections.append(
                self._build_additional_info_section(config.additional_information)
            )

        # 12. 自定义章节
        for tag_name, content in config.custom_sections.items():
            self.sections.append(f"<{tag_name}>\n{content}\n</{tag_name}>")

        # 13. 额外上下文
        if config.additional_context:
            self.sections.append(config.additional_context)

        # 拼接所有章节
        return "\n\n".join(self.sections)

    def _build_role_section(self, role: str) -> str:
        """构建角色章节."""
        return f"<your_role>\n{role}\n</your_role>"

    def _build_instructions_section(self, instructions: List[str]) -> str:
        """构建指令章节."""
        content = "<instructions>"
        if len(instructions) == 1:
            content += f"\n{instructions[0]}"
        else:
            for instruction in instructions:
                content += f"\n- {instruction}"
        content += "\n</instructions>"
        return content

    def _build_markdown_section(self) -> str:
        """构建 Markdown 格式化说明."""
        return (
            "<output_format>\n"
            "Use markdown formatting to improve readability:\n"
            "- Use headers (##, ###) to organize sections\n"
            "- Use bullet points and numbered lists\n"
            "- Use code blocks for code snippets\n"
            "- Use **bold** for emphasis\n"
            "</output_format>"
        )

    def _build_tool_instructions_section(self, tool_instructions: List[str]) -> str:
        """构建工具使用说明章节."""
        content = "<tool_usage_guidelines>"
        for instruction in tool_instructions:
            content += f"\n{instruction}"
        content += "\n</tool_usage_guidelines>"
        return content

    def _build_expected_output_section(self, expected_output: str) -> str:
        """构建期望输出章节."""
        return f"<expected_output>\n{expected_output.strip()}\n</expected_output>"

    def _build_workspace_section(self, workspace_dir: Path) -> str:
        """构建工作空间信息章节."""
        return (
            "<workspace_info>\n"
            f"Current working directory: `{workspace_dir.absolute()}`\n"
            "All relative file paths are resolved relative to this directory.\n"
            "</workspace_info>"
        )

    def _build_datetime_section(self, timezone: str = "UTC") -> str:
        """构建时间信息章节."""
        try:
            import pytz

            tz = pytz.timezone(timezone)
            now = datetime.now(tz)
            time_str = now.strftime("%Y-%m-%d %H:%M:%S %Z")
        except ImportError:
            # Fallback if pytz not available
            now = datetime.now()
            time_str = now.strftime("%Y-%m-%d %H:%M:%S")

        return f"<current_datetime>\n{time_str}\n</current_datetime>"

    def _build_additional_info_section(self, additional_info: List[str]) -> str:
        """构建额外信息章节."""
        content = "<additional_information>"
        for info in additional_info:
            content += f"\n- {info}"
        content += "\n</additional_information>"
        return content


def build_system_prompt(
    config: SystemPromptConfig,
    workspace_dir: Optional[Path] = None,
    skill_loader: Optional[SkillLoader] = None,
    tool_instructions: Optional[List[str]] = None,
) -> str:
    """便捷函数:构建系统提示.

    Args:
        config: 系统提示配置
        workspace_dir: 工作空间目录
        skill_loader: Skill 加载器
        tool_instructions: 工具使用说明

    Returns:
        系统提示字符串
    """
    builder = SystemPromptBuilder()
    return builder.build(
        config=config,
        workspace_dir=workspace_dir,
        skill_loader=skill_loader,
        tool_instructions=tool_instructions,
    )
