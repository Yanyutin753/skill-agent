# 上下文工程优化 - 快速参考

## 核心差距对比

### 当前实现
```python
# ❌ 简单字符串拼接
system_prompt = "You are a helpful assistant.\n\nWorkspace: ./workspace"
agent = Agent(system_prompt=system_prompt, ...)
```

### agno 实现
```python
# ✅ 结构化分层
<description>Agent description</description>

<your_role>
Specific role definition
</your_role>

<instructions>
- Instruction 1
- Instruction 2
</instructions>

<tool_usage>
Tool-specific instructions
</tool_usage>

<expected_output>
Output format specification
</expected_output>

<session_state>
- key: value
</session_state>

<additional_context>
Dynamic context
</additional_context>
```

## Top 5 优化建议

### 1. 结构化 System Prompt Builder 🔴
**当前:** 字符串拼接  
**改进:** XML 标签分层

```python
# 创建构建器
config = SystemPromptConfig(
    description="Agent description",
    role="Specific role",
    instructions=["Instruction 1", "Instruction 2"],
    expected_output="Output format",
    add_datetime=True
)

builder = SystemPromptBuilder(config)
prompt = builder.build()
```

**收益:** 
- ✅ 更好的 LLM 理解
- ✅ 易于维护
- ✅ 模块化

---

### 2. 上下文字段分离 🔴
**当前:** 所有内容混在一起  
**改进:** 清晰的上下文分类

agno 支持的上下文字段:
```python
add_session_state_to_context: bool      # 会话状态
add_dependencies_to_context: bool       # 依赖项
add_memories_to_context: bool           # 历史记忆
add_knowledge_to_context: bool          # 知识库
add_datetime_to_context: bool           # 时间
add_location_to_context: bool           # 位置
add_session_summary_to_context: bool    # 会话摘要
```

**当前项目只有:**
```python
system_prompt: str  # 所有内容
```

---

### 3. 工具说明自动提取 🟡
**当前:** 无工具说明  
**改进:** 工具自带使用说明

```python
class BashTool(Tool):
    @property
    def instructions(self) -> str:
        return """
        <bash_tool_usage>
        - Use absolute paths
        - Check output carefully
        </bash_tool_usage>
        """
    
    @property
    def add_to_system_prompt(self) -> bool:
        return True  # 自动添加到系统提示
```

---

### 4. 动态模板系统 🟡
**当前:** 静态 prompt  
**改进:** 支持变量和动态内容

```python
# 模板
prompt_template = """
You are {name}, a {role}.
User: {session_state.user_name}
Task: {metadata.current_task}
"""

# 动态解析
resolved = DynamicContext.resolve_template(
    prompt_template,
    variables={
        "name": "Assistant",
        "role": "helper",
        "session_state": {"user_name": "Alice"},
        "metadata": {"current_task": "Research"}
    }
)
```

---

### 5. 会话状态管理 🟡
**当前:** 无会话管理  
**改进:** 跨轮次状态保持

```python
class SessionManager:
    def get_state(self, session_id: str) -> Dict
    def update_state(self, session_id: str, updates: Dict)
    def format_state_for_context(self, session_id: str) -> str

# 使用
session_manager.update_state("user-123", {
    "user_name": "Alice",
    "preferences": {"detail_level": "high"}
})

# Agent 自动加载会话状态
agent.run(message, session_id="user-123")
```

## agno 上下文构建流程

```
1. Description           →  Agent 描述
2. Role                  →  明确角色定义
3. Instructions          →  行为指令列表
4. Tool Instructions     →  工具使用说明(自动提取)
5. Expected Output       →  输出格式规范
6. Additional Info       →  补充信息
7. Memories             →  历史记忆(如果启用)
8. Knowledge            →  知识库内容(如果启用)
9. Session State        →  会话状态(如果启用)
10. Dependencies        →  依赖项(如果启用)
11. Additional Context  →  额外上下文
```

## 当前项目构建流程

```
1. system_prompt (string)  →  所有内容
2. workspace_info          →  工作区信息
```

## 实现建议

### Phase 1: 快速改进 (1周)
```python
# 1. 添加 SystemPromptConfig
@dataclass
class SystemPromptConfig:
    description: str
    role: str
    instructions: List[str]
    expected_output: str

# 2. 添加 SystemPromptBuilder
class SystemPromptBuilder:
    def build(self, config: SystemPromptConfig) -> str:
        # 使用 XML 标签构建结构化 prompt
        pass

# 3. 修改 Agent.__init__
def __init__(
    self,
    prompt_config: SystemPromptConfig,  # 替代 system_prompt
    ...
):
    builder = SystemPromptBuilder()
    self.system_prompt = builder.build(prompt_config)
```

### Phase 2: 中期改进 (2-3周)
- 添加 AgentContext 类
- 实现动态模板解析
- 添加工具说明自动提取
- 实现基础会话管理

### Phase 3: 长期优化 (按需)
- 记忆系统
- 知识库集成
- 高级会话管理

## 关键数据对比

| 特性 | 当前 | agno | 优先级 |
|------|------|------|--------|
| 系统提示结构 | 字符串 | XML 分层 | 🔴 高 |
| 可配置字段 | 1 | 15+ | 🔴 高 |
| 动态上下文 | ❌ | ✅ | 🟡 中 |
| 工具说明 | 手动 | 自动 | 🟡 中 |
| 会话管理 | ❌ | ✅ | 🟡 中 |
| 记忆系统 | ❌ | ✅ | 🟢 低 |
| 知识库 | ❌ | ✅ | 🟢 低 |

## 示例对比

### 研究 Agent 系统提示

**当前实现:**
```
You are a research assistant. Use the tools to gather information. 
Workspace: ./workspace
```

**优化后(agno 风格):**
```xml
<description>
You are a research assistant specialized in information gathering and synthesis.
</description>

<your_role>
Information gathering and synthesis specialist
</your_role>

<instructions>
- Always cite sources when providing information
- Break down complex topics into understandable explanations  
- Use markdown formatting for better readability
- Provide comprehensive yet concise summaries
</instructions>

<tool_usage>
When using search tools:
- Verify information from multiple sources
- Prioritize recent and authoritative sources
- Include publication dates in citations
</tool_usage>

<expected_output>
Provide well-structured research summaries with:
1. Key findings
2. Supporting evidence with citations
3. Relevant context and background
4. Actionable insights
</expected_output>

<workspace_info>
Current working directory: ./workspace
All file operations are relative to this directory.
</workspace_info>

<current_datetime>
2025-11-17 14:30:00 UTC
</current_datetime>
```

**质量提升:**
- 更清晰的角色定义
- 具体的行为指导
- 明确的输出规范
- 结构化的信息组织
- 更好的 LLM 理解

## 快速实施检查清单

- [ ] 创建 `SystemPromptConfig` 数据类
- [ ] 实现 `SystemPromptBuilder` 类
- [ ] 修改 `Agent.__init__` 使用新构建器
- [ ] 为核心工具添加 `instructions` 属性
- [ ] 实现工具说明自动收集
- [ ] 添加单元测试
- [ ] 更新文档和示例

**预计时间:** 3-5 天  
**预计收益:** 显著提升 Agent 性能和可维护性
