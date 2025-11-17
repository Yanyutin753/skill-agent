# 上下文工程优化建议

基于 agno 项目的上下文管理实现,对比当前项目的差距和可优化的地方。

## 当前实现 vs agno 对比

### 1. 系统提示构建

#### 当前项目 (`src/fastapi_agent/core/agent.py`)
```python
def __init__(self, system_prompt: str, ...):
    # 简单的字符串拼接
    if "Current Workspace" not in system_prompt:
        workspace_info = f"\n\n## Current Workspace\n..."
        system_prompt = system_prompt + workspace_info

    self.system_prompt = system_prompt
    self.messages = [Message(role="system", content=system_prompt)]
```

**特点:**
- ✅ 简单直接
- ❌ 缺乏结构化
- ❌ 只支持静态 prompt
- ❌ 没有上下文分层

#### agno 实现
```python
# 结构化的上下文构建,分层清晰
system_message_content = ""

# 1. Description (Agent 描述)
if self.description:
    system_message_content += f"{self.description}\n"

# 2. Role (明确角色)
if self.role:
    system_message_content += f"\n<your_role>\n{self.role}\n</your_role>\n\n"

# 3. Instructions (指令列表)
if len(instructions) > 0:
    system_message_content += "<instructions>"
    for instruction in instructions:
        system_message_content += f"\n- {instruction}"
    system_message_content += "\n</instructions>\n\n"

# 4. Tool Instructions (工具使用说明)
if self._tool_instructions:
    for tool_instruction in self._tool_instructions:
        system_message_content += f"{tool_instruction}\n"

# 5. Expected Output (期望输出格式)
if self.expected_output:
    system_message_content += f"<expected_output>\n{self.expected_output}\n</expected_output>\n\n"

# 6. Additional Context (额外上下文)
if self.additional_context:
    system_message_content += f"{self.additional_context}\n"

# 7. Memories (历史记忆)
if self.add_memories_to_context:
    # 添加用户记忆...

# 8. Knowledge (知识库)
if self.add_knowledge_to_context:
    # 添加知识库内容...

# 9. Session State (会话状态)
if self.add_session_state_to_context:
    # 添加会话状态...

# 10. Dependencies (依赖项)
if self.add_dependencies_to_context:
    # 添加依赖项...
```

**特点:**
- ✅ 结构化,分层清晰
- ✅ 使用 XML 标签组织信息
- ✅ 支持动态上下文
- ✅ 可选模块化组件

---

## 优化建议

### 📊 优先级分类

| 优化项 | 优先级 | 实现复杂度 | 价值 |
|--------|--------|------------|------|
| 结构化系统提示构建器 | 🔴 高 | 中 | 高 |
| 上下文字段分离 | 🔴 高 | 低 | 高 |
| 动态上下文注入 | 🟡 中 | 中 | 中 |
| 会话状态管理 | 🟡 中 | 高 | 高 |
| 记忆系统 | 🟢 低 | 高 | 中 |
| 知识库集成 | 🟢 低 | 高 | 中 |

---

## 1. 结构化系统提示构建器 【优先级: 🔴 高】

### 问题
当前系统提示是一个简单字符串,缺乏结构,难以维护和扩展。

### 改进方案

创建 `SystemPromptBuilder` 类:

```python
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field


@dataclass
class SystemPromptConfig:
    """系统提示配置."""

    # 基础信息
    name: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None

    # 指令
    instructions: List[str] = field(default_factory=list)
    tool_instructions: List[str] = field(default_factory=list)

    # 输出规范
    expected_output: Optional[str] = None
    markdown: bool = False

    # 上下文控制
    add_datetime: bool = False
    add_workspace_info: bool = True

    # 额外信息
    additional_context: Optional[str] = None
    additional_information: List[str] = field(default_factory=list)


class SystemPromptBuilder:
    """构建结构化的系统提示."""

    def __init__(self, config: SystemPromptConfig):
        self.config = config

    def build(self, **dynamic_context) -> str:
        """构建系统提示.

        Args:
            **dynamic_context: 动态上下文参数

        Returns:
            构建好的系统提示字符串
        """
        sections = []

        # 1. Agent 名称和描述
        if self.config.name:
            sections.append(f"# {self.config.name}\n")

        if self.config.description:
            sections.append(self.config.description)

        # 2. 角色定义
        if self.config.role:
            sections.append(self._build_role_section())

        # 3. 指令列表
        if self.config.instructions:
            sections.append(self._build_instructions_section())

        # 4. 工具使用说明
        if self.config.tool_instructions:
            sections.append(self._build_tool_instructions_section())

        # 5. 输出格式
        if self.config.expected_output:
            sections.append(self._build_expected_output_section())

        # 6. 工作空间信息
        if self.config.add_workspace_info:
            sections.append(self._build_workspace_section(
                dynamic_context.get("workspace_dir", "./workspace")
            ))

        # 7. 时间信息
        if self.config.add_datetime:
            sections.append(self._build_datetime_section())

        # 8. 额外信息
        if self.config.additional_information:
            sections.append(self._build_additional_info_section())

        # 9. 额外上下文
        if self.config.additional_context:
            sections.append(self.config.additional_context)

        return "\n\n".join(sections)

    def _build_role_section(self) -> str:
        return f"<your_role>\n{self.config.role}\n</your_role>"

    def _build_instructions_section(self) -> str:
        content = "<instructions>"
        for instruction in self.config.instructions:
            content += f"\n- {instruction}"
        content += "\n</instructions>"
        return content

    def _build_tool_instructions_section(self) -> str:
        content = "<tool_usage>"
        for instruction in self.config.tool_instructions:
            content += f"\n{instruction}"
        content += "\n</tool_usage>"
        return content

    def _build_expected_output_section(self) -> str:
        return f"<expected_output>\n{self.config.expected_output}\n</expected_output>"

    def _build_workspace_section(self, workspace_dir: str) -> str:
        return (
            "<workspace_info>\n"
            f"Current working directory: `{workspace_dir}`\n"
            "All relative paths are resolved relative to this directory.\n"
            "</workspace_info>"
        )

    def _build_datetime_section(self) -> str:
        from datetime import datetime
        now = datetime.now()
        return (
            "<current_time>\n"
            f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            "</current_time>"
        )

    def _build_additional_info_section(self) -> str:
        content = "<additional_information>"
        for info in self.config.additional_information:
            content += f"\n- {info}"
        content += "\n</additional_information>"
        return content
```

### 使用示例

```python
# 创建配置
config = SystemPromptConfig(
    name="Research Assistant",
    description="A helpful AI assistant specialized in research and analysis.",
    role="Information gathering and synthesis specialist",
    instructions=[
        "Always cite sources when providing information",
        "Break down complex topics into understandable explanations",
        "Use markdown formatting for better readability"
    ],
    expected_output="Provide clear, well-structured responses with proper citations",
    markdown=True,
    add_datetime=True
)

# 构建系统提示
builder = SystemPromptBuilder(config)
system_prompt = builder.build(workspace_dir="./workspace")

# 在 Agent 中使用
agent = Agent(
    llm_client=llm_client,
    system_prompt=system_prompt,
    tools=[...]
)
```

**优势:**
- ✅ 结构清晰,易于维护
- ✅ 可复用配置
- ✅ 支持动态内容
- ✅ 使用 XML 标签提高 LLM 理解

---

## 2. 上下文字段分离 【优先级: 🔴 高】

### 问题
当前所有上下文混在一个字符串中,无法灵活控制。

### 改进方案

```python
@dataclass
class AgentContext:
    """Agent 运行时上下文."""

    # 基础信息
    name: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    instructions: List[str] = field(default_factory=list)

    # 动态上下文
    session_state: Dict[str, Any] = field(default_factory=dict)
    dependencies: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 上下文控制开关
    add_session_state_to_context: bool = False
    add_dependencies_to_context: bool = False
    add_datetime_to_context: bool = False
    add_workspace_to_context: bool = True


class Agent:
    def __init__(
        self,
        llm_client: LLMClient,
        context: AgentContext,
        tools: List[Tool] = None,
        ...
    ):
        self.context = context
        # ...

    def _build_system_message(self) -> str:
        """动态构建系统消息."""
        sections = []

        if self.context.description:
            sections.append(self.context.description)

        if self.context.role:
            sections.append(f"<your_role>\n{self.context.role}\n</your_role>")

        if self.context.add_session_state_to_context and self.context.session_state:
            sections.append(self._format_session_state())

        if self.context.add_datetime_to_context:
            sections.append(self._format_datetime())

        # ...

        return "\n\n".join(sections)
```

---

## 3. 动态上下文注入 【优先级: 🟡 中】

### 问题
系统提示是静态的,无法根据运行时信息动态调整。

### agno 实现

```python
# 支持可调用的 instructions
if callable(self.instructions):
    _instructions = self.instructions(**instruction_args)

# 支持模板变量替换
if self.resolve_in_context:
    system_message_content = self._format_message_with_state_variables(
        system_message_content,
        user_id=user_id,
        session_state=session_state,
        dependencies=dependencies,
        metadata=metadata,
    )
```

### 改进方案

```python
from typing import Callable

class DynamicContext:
    """动态上下文管理."""

    @staticmethod
    def resolve_template(
        template: str,
        variables: Dict[str, Any]
    ) -> str:
        """解析模板变量.

        支持格式:
        - {variable_name}
        - {session_state.key}
        - {dependencies.key}
        """
        from string import Formatter

        formatter = Formatter()
        resolved = template

        for field in formatter.parse(template):
            if field[1]:
                # 支持嵌套访问
                keys = field[1].split('.')
                value = variables
                for key in keys:
                    value = value.get(key, {})

                resolved = resolved.replace(f"{{{field[1]}}}", str(value))

        return resolved


# 使用示例
system_prompt_template = """
You are {name}, a {role}.

Session ID: {session_state.session_id}
User: {session_state.user_name}

Current task: {metadata.current_task}
"""

context_vars = {
    "name": "Assistant",
    "role": "helper",
    "session_state": {"session_id": "123", "user_name": "Alice"},
    "metadata": {"current_task": "Research"}
}

resolved = DynamicContext.resolve_template(system_prompt_template, context_vars)
```

---

## 4. 会话状态管理 【优先级: 🟡 中】

### agno 实现

```python
# 会话状态可以注入到系统提示中
if self.add_session_state_to_context and session_state:
    system_message_content += "<session_state>\n"
    for key, value in session_state.items():
        system_message_content += f"- {key}: {value}\n"
    system_message_content += "</session_state>\n\n"

# 支持 Agent 动态更新会话状态
if self.enable_agentic_state:
    # 添加 update_session_state 工具
    tools.append(update_session_state_tool)
```

### 改进方案

```python
class SessionManager:
    """会话状态管理."""

    def __init__(self):
        self.states: Dict[str, Dict[str, Any]] = {}

    def get_state(self, session_id: str) -> Dict[str, Any]:
        """获取会话状态."""
        return self.states.get(session_id, {})

    def update_state(
        self,
        session_id: str,
        updates: Dict[str, Any]
    ):
        """更新会话状态."""
        if session_id not in self.states:
            self.states[session_id] = {}

        self.states[session_id].update(updates)

    def format_state_for_context(
        self,
        session_id: str
    ) -> str:
        """格式化状态用于上下文."""
        state = self.get_state(session_id)
        if not state:
            return ""

        content = "<session_state>\n"
        for key, value in state.items():
            content += f"- {key}: {value}\n"
        content += "</session_state>"

        return content


# 在 Agent 中使用
class Agent:
    def __init__(self, session_manager: SessionManager = None, ...):
        self.session_manager = session_manager or SessionManager()

    def run(self, message: str, session_id: str = "default"):
        # 获取会话状态
        session_state = self.session_manager.get_state(session_id)

        # 添加到系统提示
        if self.add_session_state_to_context:
            state_context = self.session_manager.format_state_for_context(session_id)
            # 添加到消息中...
```

---

## 5. 工具说明自动提取 【优先级: 🔴 高】

### agno 实现

```python
# 工具可以提供自己的使用说明
class Tool:
    instructions: Optional[str] = None  # 工具使用说明
    add_instructions: bool = False      # 是否添加到系统提示

# 自动收集工具说明
self._tool_instructions = []
for tool in tools:
    if tool.add_instructions and tool.instructions:
        self._tool_instructions.append(tool.instructions)
```

### 改进方案

```python
# 修改 Tool 基类
class Tool:
    """工具基类."""

    @property
    def instructions(self) -> Optional[str]:
        """工具使用说明(可选)."""
        return None

    @property
    def add_to_system_prompt(self) -> bool:
        """是否将说明添加到系统提示."""
        return False


# 示例工具
class BashTool(Tool):
    @property
    def instructions(self) -> str:
        return """
When using the bash tool:
- Always use absolute paths when possible
- Check command output carefully before proceeding
- Use error handling for critical operations
"""

    @property
    def add_to_system_prompt(self) -> bool:
        return True


# Agent 自动收集
class Agent:
    def _collect_tool_instructions(self) -> List[str]:
        """收集需要添加到系统提示的工具说明."""
        instructions = []
        for tool in self.tools.values():
            if tool.add_to_system_prompt and tool.instructions:
                instructions.append(tool.instructions)
        return instructions
```

---

## 6. 时间和位置感知 【优先级: 🟢 低】

### agno 实现

```python
add_datetime_to_context: bool = False
add_location_to_context: bool = False
timezone_identifier: Optional[str] = None

# 在系统提示中添加
if self.add_datetime_to_context:
    from datetime import datetime
    import pytz

    tz = pytz.timezone(self.timezone_identifier or "UTC")
    now = datetime.now(tz)

    system_message_content += f"<current_datetime>\n"
    system_message_content += f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
    system_message_content += f"</current_datetime>\n\n"
```

### 改进方案

```python
from datetime import datetime
from typing import Optional


class ContextEnrichers:
    """上下文增强器."""

    @staticmethod
    def add_datetime(
        timezone: str = "UTC",
        include_timezone: bool = True
    ) -> str:
        """添加当前时间."""
        import pytz

        tz = pytz.timezone(timezone)
        now = datetime.now(tz)

        if include_timezone:
            time_str = now.strftime('%Y-%m-%d %H:%M:%S %Z')
        else:
            time_str = now.strftime('%Y-%m-%d %H:%M:%S')

        return f"<current_datetime>\n{time_str}\n</current_datetime>"

    @staticmethod
    def add_location(
        city: str,
        country: str,
        timezone: Optional[str] = None
    ) -> str:
        """添加位置信息."""
        content = "<location>\n"
        content += f"City: {city}\n"
        content += f"Country: {country}\n"
        if timezone:
            content += f"Timezone: {timezone}\n"
        content += "</location>"

        return content
```

---

## 实现优先级路线图

### Phase 1: 基础结构化 (1-2周)
1. ✅ 实现 `SystemPromptBuilder`
2. ✅ 添加 `SystemPromptConfig`
3. ✅ 修改 `Agent` 使用新的构建器
4. ✅ 添加工具说明自动提取

### Phase 2: 动态上下文 (2-3周)
1. ✅ 实现 `AgentContext` 数据类
2. ✅ 实现模板变量解析
3. ✅ 添加会话状态管理
4. ✅ 集成到 Agent

### Phase 3: 高级特性 (按需)
1. ⭕ 记忆系统集成
2. ⭕ 知识库集成
3. ⭕ 文化知识系统
4. ⭕ 时间和位置感知

---

## 代码示例:完整的改进版 Agent

```python
from fastapi_agent.core.prompt_builder import SystemPromptBuilder, SystemPromptConfig
from fastapi_agent.core.context import AgentContext, SessionManager

# 创建配置
prompt_config = SystemPromptConfig(
    name="Research Assistant",
    description="A specialized AI assistant for research and analysis",
    role="Information gathering and synthesis specialist",
    instructions=[
        "Always cite sources",
        "Provide structured, well-organized responses",
        "Use markdown for formatting"
    ],
    expected_output="Clear, well-cited research summaries",
    markdown=True,
    add_datetime=True,
    add_workspace_info=True
)

# 创建上下文
context = AgentContext(
    session_state={"user_name": "Alice", "preferences": "detailed"},
    add_session_state_to_context=True,
    add_datetime_to_context=True
)

# 创建 Agent
agent = Agent(
    llm_client=llm_client,
    prompt_config=prompt_config,
    context=context,
    tools=[...],
    session_manager=SessionManager()
)

# 运行
response = agent.run(
    "Research the benefits of async programming in Python",
    session_id="user-123"
)
```

---

## 总结

### 核心差距

| 维度 | 当前项目 | agno | 差距 |
|------|---------|------|------|
| 系统提示结构 | 字符串拼接 | XML 分层结构 | ⭐⭐⭐ |
| 上下文管理 | 静态 | 动态可配置 | ⭐⭐⭐ |
| 会话管理 | 无 | 完整支持 | ⭐⭐⭐ |
| 工具说明 | 手动 | 自动提取 | ⭐⭐ |
| 模板系统 | 无 | 变量解析 | ⭐⭐ |
| 记忆系统 | 无 | 用户记忆 | ⭐ |

### 最有价值的优化 (Top 3)

1. **结构化系统提示构建器**
   - 投入: 中
   - 收益: 高
   - 建议: 立即实施

2. **上下文字段分离和动态注入**
   - 投入: 中
   - 收益: 高
   - 建议: 短期实施

3. **工具说明自动提取**
   - 投入: 低
   - 收益: 中
   - 建议: 短期实施

这些改进将显著提升 Agent 的可维护性、可扩展性和智能性,使其更接近 agno 的工业级水平。
