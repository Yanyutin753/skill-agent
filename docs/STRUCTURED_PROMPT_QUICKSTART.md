# 结构化系统提示 - 快速开始

## 🚀 5 分钟上手

### 1. 基础使用

```python
from fastapi_agent.core.agent import Agent
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.prompt_builder import SystemPromptConfig

# 创建配置
config = SystemPromptConfig(
    name="Research Assistant",
    description="A helpful AI research assistant",
    role="Information gathering specialist",
    instructions=[
        "Always cite sources",
        "Provide clear explanations",
    ],
    expected_output="Well-structured research summaries",
    markdown=True,
)

# 创建 Agent
agent = Agent(
    llm_client=llm_client,
    prompt_config=config,  # 使用结构化配置
    tools=[...],
)
```

### 2. 集成 Skills

```python
from fastapi_agent.skills.skill_loader import SkillLoader

# 加载 Skills
skill_loader = SkillLoader(skills_dir="./skills")
skill_loader.discover_skills()

# 创建 Agent (Skills 元数据会自动添加)
agent = Agent(
    llm_client=llm_client,
    prompt_config=config,
    tools=[...],
    skill_loader=skill_loader,  # 传入 skill_loader
)
```

### 3. 工具说明自动提取

```python
from fastapi_agent.tools.base import Tool

class MyTool(Tool):
    # ... name, description, parameters ...
    
    @property
    def instructions(self) -> str:
        """工具使用说明."""
        return """
<my_tool_usage>
When using this tool:
- Follow these guidelines
- Check the output
</my_tool_usage>
"""
    
    @property
    def add_instructions_to_prompt(self) -> bool:
        """自动添加到系统提示."""
        return True
```

## 📋 配置参数详解

```python
SystemPromptConfig(
    # 基础信息
    name="Agent 名称",               # 显示在提示顶部
    description="Agent 描述",         # 开场白
    role="具体角色定义",              # <your_role> 标签
    
    # 指令 (推荐使用列表)
    instructions=[
        "指令 1",
        "指令 2",
    ],
    
    # 输出规范
    expected_output="期望的输出格式",
    markdown=True,                   # 添加 markdown 格式说明
    
    # 上下文
    add_datetime_to_context=True,    # 添加当前时间
    add_workspace_info=True,         # 添加工作空间路径
    timezone="Asia/Shanghai",        # 时区
    
    # 额外内容
    additional_information=[         # 额外信息列表
        "额外信息 1",
        "额外信息 2",
    ],
    additional_context="自由文本",    # 添加到末尾
)
```

## 🎯 实战示例

### 示例 1: Python 开发 Agent

```python
config = SystemPromptConfig(
    name="Python Developer Pro",
    description="An expert Python developer with deep knowledge of best practices",
    role="Senior Python Developer",
    instructions=[
        "Write clean, PEP 8 compliant code",
        "Include comprehensive docstrings",
        "Handle errors gracefully",
        "Add type hints where appropriate",
    ],
    expected_output="Production-ready Python code with tests and documentation",
    markdown=True,
    add_datetime_to_context=True,
)

agent = Agent(
    llm_client=llm_client,
    prompt_config=config,
    tools=[ReadTool(), WriteTool(), BashTool()],
    skill_loader=skill_loader,
)
```

### 示例 2: 数据分析 Agent

```python
config = SystemPromptConfig(
    name="Data Analyst",
    description="A data analysis specialist skilled in Python and statistics",
    role="Data Analysis Expert",
    instructions=[
        "Provide statistical insights",
        "Create clear visualizations",
        "Explain methodology clearly",
    ],
    expected_output="Data analysis reports with visualizations and insights",
    markdown=True,
    additional_information=[
        "Prefer pandas and matplotlib for analysis",
        "Use statistical tests when appropriate",
    ],
)
```

### 示例 3: 系统管理 Agent

```python
config = SystemPromptConfig(
    name="SysAdmin Assistant",
    description="A system administration helper for Linux servers",
    role="System Administrator",
    instructions=[
        "Execute commands safely",
        "Always verify results",
        "Use sudo only when necessary",
        "Explain actions before executing",
    ],
    expected_output="Command results with clear explanations",
    add_datetime_to_context=True,
)

agent = Agent(
    llm_client=llm_client,
    prompt_config=config,
    tools=[BashTool()],  # BashTool 的说明会自动添加!
)
```

## 📊 对比: 旧 vs 新

### ❌ 旧方式

```python
system_prompt = """
You are a Python developer.
Write clean code.
Follow PEP 8.
Use markdown.
Current workspace: ./workspace
"""

agent = Agent(
    llm_client=llm_client,
    system_prompt=system_prompt,
    tools=[...],
)
```

**问题:**
- 字符串混乱,难以维护
- 没有结构化
- 无法自动注入 Skills 和工具说明
- 难以复用

### ✅ 新方式

```python
config = SystemPromptConfig(
    description="You are a Python developer",
    instructions=[
        "Write clean code",
        "Follow PEP 8",
    ],
    markdown=True,
)

agent = Agent(
    llm_client=llm_client,
    prompt_config=config,
    tools=[...],
    skill_loader=skill_loader,
)
```

**优势:**
- ✅ 结构清晰
- ✅ 易于维护
- ✅ 自动注入 Skills 和工具说明
- ✅ 可复用配置
- ✅ XML 标签增强 LLM 理解

## 🔍 生成的提示示例

```xml
# Python Developer Pro

An expert Python developer with deep knowledge of best practices

<your_role>
Senior Python Developer
</your_role>

<instructions>
- Write clean, PEP 8 compliant code
- Include comprehensive docstrings
- Handle errors gracefully
- Add type hints where appropriate
</instructions>

<output_format>
Use markdown formatting to improve readability:
- Use headers (##, ###) to organize sections
- Use bullet points and numbered lists
- Use code blocks for code snippets
</output_format>

<tool_usage_guidelines>
<bash_tool_usage>
When using the bash tool:
- Always use absolute paths
- Check command output carefully
...
</bash_tool_usage>
</tool_usage_guidelines>

## Available Skills

You have access to specialized skills...
- `web-tools`: Web scraping, API interaction...

<expected_output>
Production-ready Python code with tests and documentation
</expected_output>

<workspace_info>
Current working directory: /absolute/path/to/workspace
</workspace_info>

<current_datetime>
2025-11-17 11:43:44 UTC
</current_datetime>
```

## 🎓 最佳实践

### 1. 使用具体的角色
❌ `role="Helper"`
✅ `role="Senior Python Developer with 10+ years experience"`

### 2. 指令要具体可执行
❌ `instructions=["Be good"]`
✅ `instructions=["Follow PEP 8", "Add type hints", "Write docstrings"]`

### 3. 明确期望输出
❌ `expected_output="Good results"`
✅ `expected_output="Production-ready code with tests, documentation, and error handling"`

### 4. 善用 markdown
```python
markdown=True  # 让 LLM 输出更美观
```

### 5. 添加时间感知
```python
add_datetime_to_context=True  # 对时间敏感的任务很有用
```

## 🔧 高级技巧

### 自定义章节

```python
config = SystemPromptConfig(
    # ... 基础配置 ...
    custom_sections={
        "coding_standards": """
Our team follows these standards:
- Use Black for formatting
- Max line length: 88
- Type hints required
""",
        "security_guidelines": """
Security requirements:
- Never log sensitive data
- Validate all inputs
- Use parameterized queries
""",
    },
)
```

### 动态内容

```python
from datetime import datetime

config = SystemPromptConfig(
    description=f"Today is {datetime.now().strftime('%A')}",
    instructions=[
        "Adjust recommendations based on the day of week",
    ],
)
```

## 🚦 迁移指南

如果你有旧代码,逐步迁移:

**Step 1:** 保持旧代码运行
```python
# 旧代码仍然工作
agent = Agent(
    llm_client=llm_client,
    system_prompt="You are...",  # 向后兼容
)
```

**Step 2:** 逐步替换为配置
```python
config = SystemPromptConfig(
    description="You are...",
    # ... 转换其他部分 ...
)

agent = Agent(
    llm_client=llm_client,
    prompt_config=config,  # 新方式
)
```

**Step 3:** 添加 Skills 和工具说明
```python
agent = Agent(
    llm_client=llm_client,
    prompt_config=config,
    skill_loader=skill_loader,  # 自动注入 Skills
    tools=[BashTool()],         # 自动注入工具说明
)
```

## 📚 更多资源

- 完整文档: `docs/CONTEXT_ENGINEERING_IMPLEMENTATION.md`
- 测试示例: `examples/test_structured_prompt.py`
- API 参考: `src/fastapi_agent/core/prompt_builder.py`

## ❓ 常见问题

**Q: 旧代码会不会坏?**
A: 不会,完全向后兼容。

**Q: 必须用新方式吗?**
A: 不是必须,但强烈推荐。新方式更清晰,功能更强大。

**Q: Skills 必须传吗?**
A: 不是必须,但如果有 Skills,传 `skill_loader` 会自动注入元数据。

**Q: 工具说明会自动添加吗?**
A: 是的,如果工具设置了 `add_instructions_to_prompt=True`。

**Q: 可以混用新旧方式吗?**
A: 可以,但一个 Agent 只能用一种方式 (要么 `system_prompt`,要么 `prompt_config`)。

## ✨ 总结

使用结构化系统提示构建器,你将获得:

1. ✅ **更好的 LLM 性能** - 结构化提示提升理解度
2. ✅ **更易维护** - 配置化管理,清晰明了
3. ✅ **自动化** - Skills 和工具说明自动注入
4. ✅ **可复用** - 配置可以保存和共享

立即开始使用,让你的 Agent 更专业! 🚀
