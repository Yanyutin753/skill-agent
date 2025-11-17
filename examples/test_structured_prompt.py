"""
测试结构化系统提示构建器

演示如何使用新的 SystemPromptConfig 和 skill 集成。
"""

import os
from dotenv import load_dotenv

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.prompt_builder import SystemPromptConfig
from fastapi_agent.skills.skill_loader import SkillLoader
from fastapi_agent.tools.bash_tool import BashTool
from fastapi_agent.tools.file_tools import ReadTool, WriteTool

load_dotenv()


def test_basic_structured_prompt():
    """测试基础的结构化提示."""
    print("=" * 80)
    print("测试 1: 基础结构化提示")
    print("=" * 80)

    # 创建配置
    config = SystemPromptConfig(
        name="Research Assistant",
        description="A specialized AI assistant for research and documentation.",
        role="Information gathering and synthesis specialist",
        instructions=[
            "Always cite sources when providing information",
            "Break down complex topics into understandable explanations",
            "Use markdown formatting for better readability",
        ],
        expected_output="Provide well-structured responses with proper citations",
        markdown=True,
        add_datetime_to_context=True,
    )

    # 创建 LLM 客户端
    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE"),
    )

    # 创建 Agent (使用新的配置方式)
    agent = Agent(
        llm_client=llm_client,
        prompt_config=config,
        tools=[BashTool()],
        enable_logging=False,
    )

    # 打印生成的系统提示
    print("\n生成的系统提示:\n")
    print(agent.system_prompt)
    print("\n" + "=" * 80 + "\n")


def test_with_skills():
    """测试包含 skills 的结构化提示."""
    print("=" * 80)
    print("测试 2: 包含 Skills 的结构化提示")
    print("=" * 80)

    # 加载 skills
    skill_loader = SkillLoader(skills_dir="./skills")
    skills = skill_loader.discover_skills()
    print(f"\n✅ 加载了 {len(skills)} 个 skills:")
    for skill in skills:
        print(f"  - {skill.name}: {skill.description}")

    # 创建配置
    config = SystemPromptConfig(
        name="Python Developer",
        description="An expert Python developer with access to specialized skills.",
        role="Software development specialist",
        instructions=[
            "Write clean, well-documented code",
            "Follow Python best practices",
            "Use available skills for specialized guidance",
        ],
        expected_output="Provide clear, working code with explanations",
        markdown=True,
    )

    # 创建 LLM 客户端
    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE"),
    )

    # 创建 Agent (包含 skill_loader)
    agent = Agent(
        llm_client=llm_client,
        prompt_config=config,
        tools=[ReadTool(), WriteTool(), BashTool()],
        skill_loader=skill_loader,  # 传入 skill_loader
        enable_logging=False,
    )

    # 打印生成的系统提示
    print("\n生成的系统提示:\n")
    print(agent.system_prompt)
    print("\n" + "=" * 80 + "\n")

    # 检查 skills 元数据是否在提示中
    if "Available Skills" in agent.system_prompt:
        print("✅ Skills 元数据已成功注入到系统提示!")
    else:
        print("❌ Skills 元数据未找到!")


def test_tool_instructions():
    """测试工具说明自动提取."""
    print("=" * 80)
    print("测试 3: 工具说明自动提取")
    print("=" * 80)

    config = SystemPromptConfig(
        name="System Administrator",
        description="A system administration assistant with bash access.",
        instructions=[
            "Execute commands carefully",
            "Always verify results",
        ],
    )

    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE"),
    )

    # BashTool 有 instructions 并且 add_instructions_to_prompt=True
    agent = Agent(
        llm_client=llm_client,
        prompt_config=config,
        tools=[BashTool()],
        enable_logging=False,
    )

    print("\n生成的系统提示:\n")
    print(agent.system_prompt)
    print("\n" + "=" * 80 + "\n")

    # 检查工具说明是否在提示中
    if "bash_tool_usage" in agent.system_prompt:
        print("✅ BashTool 说明已成功添加到系统提示!")
    else:
        print("❌ BashTool 说明未找到!")


def test_backward_compatibility():
    """测试向后兼容性 - 旧方式仍然工作."""
    print("=" * 80)
    print("测试 4: 向后兼容性 (旧的 system_prompt 参数)")
    print("=" * 80)

    llm_client = LLMClient(
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "openai:gpt-4o-mini"),
        api_base=os.getenv("LLM_API_BASE"),
    )

    # 使用旧方式: 直接传 system_prompt 字符串
    agent = Agent(
        llm_client=llm_client,
        system_prompt="You are a helpful assistant.",
        tools=[],
        enable_logging=False,
    )

    print("\n生成的系统提示:\n")
    print(agent.system_prompt)
    print("\n" + "=" * 80 + "\n")

    if "helpful assistant" in agent.system_prompt:
        print("✅ 向后兼容性正常!")
    else:
        print("❌ 向后兼容性有问题!")


def main():
    """运行所有测试."""
    tests = [
        ("基础结构化提示", test_basic_structured_prompt),
        ("包含 Skills", test_with_skills),
        ("工具说明自动提取", test_tool_instructions),
        ("向后兼容性", test_backward_compatibility),
    ]

    for name, test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"❌ 测试失败: {name}")
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
        print("\n")


if __name__ == "__main__":
    main()
