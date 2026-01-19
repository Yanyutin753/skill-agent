"""预定义场景配置注册表。"""

from typing import Dict

from omni_agent.core.scene import SceneConfig, SceneType

SCENE_CONFIGS: Dict[SceneType, SceneConfig] = {
    SceneType.GENERAL: SceneConfig(
        scene_type=SceneType.GENERAL,
        execution_mode="single",
        priority=0,
    ),
    SceneType.CODE_DEVELOPMENT: SceneConfig(
        scene_type=SceneType.CODE_DEVELOPMENT,
        execution_mode="single",
        tool_preset="coding",
        enable_rag=False,
        system_prompt_prefix="你是一个专业的软件开发助手，擅长代码编写、调试和优化。",
        max_steps=30,
        enable_spawn_agent=True,
        priority=10,
        keywords=[
            "代码",
            "编程",
            "开发",
            "调试",
            "bug",
            "实现",
            "函数",
            "类",
            "API",
            "重构",
            "优化代码",
            "code",
            "programming",
            "debug",
            "implement",
            "function",
            "class",
            "refactor",
            "fix",
            "error",
            "exception",
        ],
    ),
    SceneType.TRAVEL_PLANNING: SceneConfig(
        scene_type=SceneType.TRAVEL_PLANNING,
        execution_mode="single",
        tool_preset="travel",
        suggested_skills=["travel-planner"],
        system_prompt_prefix="你是一个专业的旅行规划助手。优先使用高德地图工具获取路线、天气和周边信息。",
        max_steps=20,
        priority=15,
        keywords=[
            "旅游",
            "旅行",
            "出行",
            "景点",
            "路线",
            "酒店",
            "机票",
            "攻略",
            "导航",
            "天气",
            "周边",
            "附近",
            "travel",
            "trip",
            "destination",
            "hotel",
            "flight",
            "itinerary",
            "route",
            "weather",
        ],
    ),
    SceneType.INFORMATION_RETRIEVAL: SceneConfig(
        scene_type=SceneType.INFORMATION_RETRIEVAL,
        execution_mode="single",
        tool_preset="research",
        enable_rag=True,
        system_prompt_prefix="你是一个信息检索助手。先搜索本地知识库，如无结果再使用网络搜索。",
        max_steps=15,
        priority=5,
        keywords=[
            "搜索",
            "查找",
            "了解",
            "是什么",
            "怎么样",
            "最新",
            "新闻",
            "资讯",
            "search",
            "find",
            "what is",
            "how to",
            "latest",
            "news",
        ],
    ),
    SceneType.WEB_RESEARCH: SceneConfig(
        scene_type=SceneType.WEB_RESEARCH,
        execution_mode="team",
        team_config_name="web_research",
        system_prompt_prefix="协调团队完成深度网络研究任务，综合多个来源的信息。",
        max_steps=50,
        priority=12,
        keywords=[
            "深度调研",
            "综合分析",
            "多源对比",
            "详细研究",
            "research",
            "comprehensive",
            "in-depth",
        ],
    ),
    SceneType.DOCUMENT_PROCESSING: SceneConfig(
        scene_type=SceneType.DOCUMENT_PROCESSING,
        execution_mode="single",
        tool_preset="minimal",
        suggested_skills=["artifacts-builder"],
        system_prompt_prefix="你是一个文档处理专家，擅长文档创建、编辑、格式化和内容转换。",
        max_steps=20,
        priority=8,
        keywords=[
            "文档",
            "PDF",
            "报告",
            "总结",
            "摘要",
            "翻译",
            "格式",
            "Word",
            "Markdown",
            "document",
            "PDF",
            "report",
            "summary",
            "translate",
            "format",
        ],
    ),
    SceneType.DATA_ANALYSIS: SceneConfig(
        scene_type=SceneType.DATA_ANALYSIS,
        execution_mode="single",
        tool_groups=["file_ops", "code_tools"],
        system_prompt_prefix="你是一个数据分析专家。可以使用 Python 进行数据处理、分析和可视化。",
        max_steps=25,
        enable_spawn_agent=True,
        priority=10,
        keywords=[
            "数据分析",
            "统计",
            "图表",
            "可视化",
            "Excel",
            "CSV",
            "数据处理",
            "分析数据",
            "data analysis",
            "statistics",
            "chart",
            "visualization",
            "pandas",
            "numpy",
        ],
    ),
}


def get_scene_config(scene_type: SceneType) -> SceneConfig:
    """根据类型获取场景配置。

    Args:
        scene_type: 场景类型

    Returns:
        指定类型的 SceneConfig，未找到则返回 GENERAL
    """
    return SCENE_CONFIGS.get(scene_type, SCENE_CONFIGS[SceneType.GENERAL])


def get_all_scene_types() -> list[SceneType]:
    """获取所有可用的场景类型。

    Returns:
        所有 SceneType 值的列表
    """
    return list(SceneType)
