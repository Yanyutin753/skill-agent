# Team Feature - 多 Agent 协作系统

Team 功能允许你创建由多个专业 Agent 组成的团队,通过 Team Leader 协调各个成员完成复杂任务。

## 核心概念

### 架构设计

```
┌─────────────────────────────────────┐
│         Team Leader (LLM)           │
│  - 分析任务                          │
│  - 选择合适的成员                    │
│  - 委派任务                          │
│  - 综合结果                          │
└────────────┬────────────────────────┘
             │
    ┌────────┴────────┐
    │ Delegation Tool │
    └────────┬────────┘
             │
    ┌────────┴─────────────────┐
    │                          │
┌───▼────┐  ┌────▼────┐  ┌───▼────┐
│Member 1│  │Member 2 │  │Member 3│
│(Agent) │  │(Agent)  │  │(Agent) │
└────────┘  └─────────┘  └────────┘
```

### 委派模式

1. **选择性委派** (`delegate_to_all=False`)
   - Leader 根据任务选择最合适的成员
   - 可以委派给多个成员
   - 可以根据反馈重新委派

2. **全员委派** (`delegate_to_all=True`)  
   - Leader 将任务发送给所有成员
   - 获取多样化的视角
   - 适合创意头脑风暴

## 快速开始

### 1. 定义团队配置

```python
from fastapi_agent.schemas.team import TeamConfig, TeamMemberConfig

team_config = TeamConfig(
    name="Research Team",
    description="专门从事研究和文档编写的团队",
    members=[
        TeamMemberConfig(
            name="研究员",
            role="信息收集专家",
            instructions="负责查找和总结相关信息",
            tools=[]  # 可用工具列表
        ),
        TeamMemberConfig(
            name="作家",
            role="文档编写专家", 
            instructions="创建清晰、结构良好的文档",
            tools=["write_file"]
        )
    ],
    leader_instructions="协调团队,将研究任务委派给研究员,文档任务委派给作家",
    delegate_to_all=False
)
```

### 2. 创建并运行团队

```python
from fastapi_agent.core.team import Team
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.tools.base_tools import WriteTool

# 创建 LLM 客户端
llm_client = LLMClient(
    api_key="your-api-key",
    model="openai:gpt-4o-mini"
)

# 创建团队
team = Team(
    config=team_config,
    llm_client=llm_client,
    available_tools=[WriteTool()],
    workspace_dir="./workspace"
)

# 运行任务
response = team.run("研究 Python asyncio 并创建总结文档")

# 查看结果
print(f"成功: {response.success}")
print(f"最终响应: {response.message}")
print(f"成员运行次数: {response.iterations}")

for member_run in response.member_runs:
    print(f"{member_run.member_name}: {member_run.response}")
```

## 示例场景

### 1. 研究团队

适用于需要信息收集、分析和文档编写的任务。

```python
research_team = TeamConfig(
    name="Research Team",
    members=[
        TeamMemberConfig(name="Researcher", role="信息收集", tools=[]),
        TeamMemberConfig(name="Analyst", role="数据分析", tools=[]),
        TeamMemberConfig(name="Writer", role="文档编写", tools=["write_file"])
    ],
    delegate_to_all=False
)
```

### 2. 开发团队

适用于软件开发任务,包括设计、实现和测试。

```python
dev_team = TeamConfig(
    name="Development Team",
    members=[
        TeamMemberConfig(name="Architect", role="架构设计", tools=[]),
        TeamMemberConfig(name="Developer", role="代码实现", 
                        tools=["write_file", "read_file", "edit_file"]),
        TeamMemberConfig(name="QA", role="质量保证", 
                        tools=["read_file", "bash"])
    ],
    leader_instructions="按顺序: 架构师设计 -> 开发者实现 -> QA 测试"
)
```

### 3. 创意团队

适用于需要多样化视角的创意任务。

```python
creative_team = TeamConfig(
    name="Creative Team",
    members=[
        TeamMemberConfig(name="Innovator", role="创新思维", tools=[]),
        TeamMemberConfig(name="Pragmatist", role="实用评估", tools=[]),
        TeamMemberConfig(name="Synthesizer", role="整合综合", tools=[])
    ],
    delegate_to_all=True  # 获取所有成员的输入
)
```

## API 参考

### TeamConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| name | str | 必填 | 团队名称 |
| description | str | None | 团队描述 |
| members | List[TeamMemberConfig] | 必填 | 团队成员列表 |
| model | str | "openai:gpt-4o-mini" | LLM 模型 |
| leader_instructions | str | None | Leader 的指导说明 |
| delegate_to_all | bool | False | 是否委派给所有成员 |
| max_iterations | int | 10 | 最大委派迭代次数 |

### TeamMemberConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| name | str | 必填 | 成员名称 |
| role | str | 必填 | 成员角色/专长 |
| instructions | str | None | 成员的具体指导 |
| tools | List[str] | [] | 可用工具名称列表 |
| model | str | None | 成员的 LLM 模型 (默认使用团队模型) |

### TeamRunResponse

| 字段 | 类型 | 说明 |
|------|------|------|
| success | bool | 是否成功 |
| team_name | str | 团队名称 |
| message | str | 最终响应消息 |
| member_runs | List[MemberRunResult] | 成员运行记录 |
| total_steps | int | 总步骤数 |
| iterations | int | 迭代次数 |
| metadata | dict | 元数据 |

## 运行示例

```bash
# 运行团队演示
uv run python examples/team_demo.py

# 运行测试
uv run pytest tests/core/test_team.py -v
```

## 实现原理

### 委派流程

1. **Leader 接收任务**
   - 分析任务需求
   - 识别所需技能

2. **工具调用**
   - Leader 使用 `delegate_task_to_member` 工具
   - 指定成员和任务描述

3. **成员执行**
   - 创建成员 Agent 实例
   - 分配专属工具
   - 执行任务

4. **结果收集**
   - 收集成员响应
   - 更新团队上下文

5. **综合分析**
   - Leader 分析所有响应
   - 决定是否需要更多委派
   - 生成最终答案

### 关键特性

- ✅ **动态工具分配**: 每个成员只能访问其配置的工具
- ✅ **上下文隔离**: 成员之间不共享执行历史
- ✅ **递归委派**: Leader 可以多次委派直到满意
- ✅ **执行追踪**: 记录所有成员运行和步骤
- ✅ **错误处理**: 成员失败不会导致整个团队失败

## 最佳实践

1. **明确角色**: 为每个成员定义清晰的角色和职责
2. **工具分配**: 只给成员分配其需要的工具
3. **Leader 指导**: 提供清晰的委派策略给 Leader
4. **迭代控制**: 设置合理的 max_iterations 避免无限循环
5. **任务分解**: 复杂任务应该分解为可管理的子任务

## 与 agno Team 的对比

| 特性 | 本实现 | agno |
|------|--------|------|
| 核心概念 | ✅ Leader + Members | ✅ Leader + Members |
| 委派工具 | ✅ delegate_task_to_member | ✅ delegate_task_to_member |
| 全员委派 | ✅ delegate_task_to_all_members | ✅ delegate_task_to_all_members |
| 工具分配 | ✅ 基于配置 | ✅ 基于配置 |
| 会话管理 | ❌ 简化版 | ✅ 完整支持 |
| 嵌套团队 | ❌ 不支持 | ✅ 支持 |
| 流式输出 | ❌ 暂不支持 | ✅ 支持 |
| 记忆管理 | ❌ 不支持 | ✅ 支持 |

本实现专注于核心的任务委派功能,提供了一个简洁、易用的多 Agent 协作方案。

## 故障排除

### 问题: Leader 不委派任务

**原因**: Leader 的系统提示不够明确

**解决**: 在 `leader_instructions` 中明确说明何时委派

### 问题: 成员无法使用工具

**原因**: 工具名称不匹配或工具未在 available_tools 中

**解决**: 检查 `tools` 列表和 `available_tools` 参数

### 问题: 迭代次数过多

**原因**: Leader 反复委派相同任务

**解决**: 
- 降低 `max_iterations`
- 优化 Leader 指导说明
- 检查成员响应质量

## 后续扩展

可能的扩展方向:

- [ ] 支持流式输出
- [ ] 添加会话记忆
- [ ] 支持嵌套团队
- [ ] 并行执行成员任务
- [ ] 添加团队级工具
- [ ] 支持动态成员添加/移除
