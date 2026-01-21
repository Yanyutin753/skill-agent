"""常见用例的内置团队配置。"""
from typing import List

from omni_agent.core.llm_client import LLMClient
from omni_agent.core.team import Team
from omni_agent.schemas.team import TeamConfig, TeamMemberConfig
from omni_agent.tools.base import Tool


def create_web_research_team(
    llm_client: LLMClient,
    available_tools: List[Tool],
    workspace_dir: str = "./workspace",
) -> Team:
    """Create a builtin web research team with search and spider capabilities.

    This team consists of two specialized agents:
    1. Web Search Agent - Uses exa MCP tools for web searching
    2. Web Spider Agent - Uses firecrawl MCP tools for web crawling

    Args:
        llm_client: LLM client instance
        available_tools: All available tools (including MCP tools)
        workspace_dir: Workspace directory for file operations

    Returns:
        Configured Team instance

    Example:
        >>> team = create_web_research_team(llm_client, mcp_tools)
        >>> response = await team.run(
        ...     message="Search for AI news and crawl the top article",
        ...     session_id="user-123"
        ... )
    """
    # Filter tools by name prefix or type
    exa_tools = [t.name for t in available_tools if "exa" in t.name.lower() or "search" in t.name.lower()]
    firecrawl_tools = [t.name for t in available_tools if "firecrawl" in t.name.lower() or "crawl" in t.name.lower()]

    config = TeamConfig(
        name="Web Research Team",
        description="A specialized team for web searching and content extraction",
        members=[
            TeamMemberConfig(
                id="web_search_agent",
                name="Web Search Agent",
                role="Web Search Specialist",
                instructions=(
                    "You are a web search specialist. Use the exa search tools to find "
                    "relevant web content, articles, and information. Provide clear summaries "
                    "of search results with URLs."
                ),
                tools=exa_tools,
            ),
            TeamMemberConfig(
                id="web_spider_agent",
                name="Web Spider Agent",
                role="Web Crawling Specialist",
                instructions=(
                    "You are a web crawling specialist. Use firecrawl tools to extract "
                    "content from web pages. Provide clean, structured content from the "
                    "crawled pages."
                ),
                tools=firecrawl_tools,
            ),
        ],
        leader_instructions=(
            "Coordinate the web research team efficiently:\n"
            "1. For search queries, delegate to the Web Search Agent\n"
            "2. For content extraction from URLs, delegate to the Web Spider Agent\n"
            "3. You can delegate to both agents for comprehensive research:\n"
            "   - First search for relevant content\n"
            "   - Then crawl specific URLs to extract detailed information"
        ),
    )

    return Team(
        config=config,
        llm_client=llm_client,
        available_tools=available_tools,
        workspace_dir=workspace_dir,
    )


def create_default_team(
    llm_client: LLMClient,
    available_tools: List[Tool],
    workspace_dir: str = "./workspace",
) -> Team:
    """创建默认的通用任务执行团队。

    团队包含三个专业子 Agent：
    1. General - 处理简单任务、问答、基础文件操作
    2. Coder - 处理代码编写、修改、调试
    3. Researcher - 处理信息搜索、网页内容获取

    Leader 只负责任务分配和结果汇总，不直接执行任务。

    Args:
        llm_client: LLM 客户端实例
        available_tools: 所有可用工具（包括 MCP 工具）
        workspace_dir: 工作空间目录

    Returns:
        配置好的 Team 实例
    """
    general_tools = ["read_file", "bash"]
    coder_tools = ["read_file", "write_file", "edit_file", "bash"]
    researcher_tools = [
        t.name for t in available_tools
        if any(kw in t.name.lower() for kw in ["search", "exa", "fetch", "firecrawl", "crawl", "web"])
    ]

    config = TeamConfig(
        name="Default Team",
        description="通用任务执行团队",
        members=[
            TeamMemberConfig(
                id="general",
                name="General",
                role="通用任务执行者",
                instructions=(
                    "你是一个通用任务执行者，负责处理简单的问答、文件查看和基础操作。"
                    "你可以读取文件内容、执行简单的 shell 命令来获取信息。"
                    "对于复杂的代码修改或网络搜索任务，应该由其他专业 Agent 处理。"
                ),
                tools=general_tools,
            ),
            TeamMemberConfig(
                id="coder",
                name="Coder",
                role="代码开发专家",
                instructions=(
                    "你是一个代码开发专家，负责编写、修改和调试代码。"
                    "你可以读取、写入、编辑文件，以及执行 shell 命令来运行测试或构建项目。"
                    "确保代码质量，遵循项目的代码风格和最佳实践。"
                ),
                tools=coder_tools,
            ),
            TeamMemberConfig(
                id="researcher",
                name="Researcher",
                role="信息研究专家",
                instructions=(
                    "你是一个信息研究专家，负责搜索和获取网络信息。"
                    "你可以使用搜索工具查找相关内容，使用爬虫工具提取网页信息。"
                    "提供清晰、结构化的搜索结果和内容摘要。"
                ),
                tools=researcher_tools,
            ),
        ],
        leader_instructions=(
            "你是任务协调者，负责分析用户任务并分配给合适的团队成员执行。\n\n"
            "分配策略：\n"
            "- 简单问答、文件查看、基础信息获取 → General\n"
            "- 代码编写、修改、调试、项目构建 → Coder\n"
            "- 网络搜索、网页内容获取、信息研究 → Researcher\n"
            "- 复合任务 → 按顺序委派多个 Agent（如先 Researcher 搜索，再 Coder 实现）\n\n"
            "你不直接执行任务，只负责分析、分配和汇总各 Agent 的执行结果。"
        ),
    )

    return Team(
        config=config,
        llm_client=llm_client,
        available_tools=available_tools,
        workspace_dir=workspace_dir,
    )
