# Agent 追踪与日志系统指南

## 概述

本项目提供两层日志系统：
1. **AgentLogger**: 单个 Agent 的详细执行日志
2. **TraceLogger**: 多 Agent 工作流的追踪日志

## 当前日志架构

### AgentLogger（已有）

**位置**: `~/.fastapi-agent/log/agent_run_*.log`

**记录内容**：
- ✅ 单个 Agent 的 STEP、LLM 请求/响应
- ✅ 工具调用和执行结果
- ✅ Token 使用统计
- ✅ 执行时间

**不足**：
- ❌ 缺少 Agent 间的流转信息
- ❌ 无法追踪 Team 的委派过程
- ❌ 依赖工作流的层级关系不清晰

### TraceLogger（新增）

**位置**: `~/.fastapi-agent/traces/trace_*.jsonl`

**记录内容**：
- ✅ 完整的工作流生命周期
- ✅ Agent 启动/结束及嵌套层级
- ✅ 任务依赖关系和执行层级
- ✅ Leader 向 Member 的委派记录
- ✅ 任务间的消息传递
- ✅ 跨 Agent 的统一 trace_id

## 使用方式

### 1. 在 Team 中集成 TraceLogger

```python
# team.py
from fastapi_agent.core.trace_logger import TraceLogger, TraceEventType

class Team:
    def __init__(self, ...):
        self.trace_logger = TraceLogger()

    async def run(self, message: str):
        # 开始追踪
        trace_id = self.trace_logger.start_trace(
            trace_type="team",
            metadata={
                "team_name": self.config.name,
                "members": [m.name for m in self.config.members]
            }
        )

        try:
            # Leader 开始执行
            self.trace_logger.log_agent_start(
                agent_name="Leader",
                agent_role="Team Leader",
                task=message,
                depth=0
            )

            # ... Leader 执行逻辑 ...

            # 结束追踪
            self.trace_logger.log_agent_end(
                agent_name="Leader",
                success=True,
                result=response_content,
                steps=leader_steps
            )

            self.trace_logger.end_trace(success=True, result=response_content)
        except Exception as e:
            self.trace_logger.end_trace(success=False, result=str(e))
            raise
```

### 2. 在 DelegateTaskTool 中记录委派

```python
# team.py
class DelegateTaskTool(Tool):
    async def execute(self, member_name: str, task: str):
        # 记录委派
        if hasattr(self.team, 'trace_logger'):
            self.team.trace_logger.log_delegation(
                from_agent="Leader",
                to_member=member_name,
                task=task
            )

        # Member 开始执行
        self.team.trace_logger.log_agent_start(
            agent_name=member_name,
            agent_role=member_config.role,
            task=task,
            parent_agent="Leader",
            depth=1
        )

        result = await self.team._run_member(member_config, task)

        # Member 结束
        self.trace_logger.log_agent_end(
            agent_name=member_name,
            success=result.success,
            result=result.response,
            steps=result.steps
        )
```

### 3. 在依赖工作流中记录任务流转

```python
# team.py
async def run_with_dependencies(self, tasks: List[TaskWithDependencies]):
    trace_id = self.trace_logger.start_trace(
        trace_type="dependency_workflow",
        metadata={
            "team_name": self.config.name,
            "task_count": len(tasks),
            "execution_order": [[task.id for task in layer] for layer in layers]
        }
    )

    layers = self._resolve_dependencies(tasks)

    for layer_idx, layer in enumerate(layers):
        # 记录任务开始
        for task in layer:
            self.trace_logger.log_task_start(
                task_id=task.id,
                task_description=task.task,
                assigned_to=task.assigned_to,
                depends_on=task.depends_on,
                layer=layer_idx
            )

        # 执行任务
        results = await asyncio.gather(*[
            self._execute_task_with_context(task, completed_results)
            for task in layer
        ])

        # 记录任务结束和消息传递
        for task in results:
            self.trace_logger.log_task_end(
                task_id=task.id,
                status=task.status,
                result=task.result,
                elapsed=task.metadata.get("elapsed")
            )

            # 记录向依赖任务传递消息
            for dep_task_id in find_dependent_tasks(task.id):
                self.trace_logger.log_message_pass(
                    from_task=task.id,
                    to_task=dep_task_id,
                    message_preview=task.result
                )
```

## 查看追踪日志

### 方法 1: 命令行工具

```bash
# 列出最近的追踪
uv run python -m fastapi_agent.utils.trace_viewer list

# 查看详细追踪
uv run python -m fastapi_agent.utils.trace_viewer view trace_team_20251205_abc123.jsonl

# 可视化工作流
uv run python -m fastapi_agent.utils.trace_viewer flow trace_dependency_workflow_20251205_xyz789.jsonl
```

### 方法 2: Python 脚本

```python
from fastapi_agent.utils.trace_viewer import TraceViewer

viewer = TraceViewer()
viewer.list_traces(limit=5)
viewer.view_trace("trace_team_20251205_abc123.jsonl")
viewer.visualize_flow("trace_dependency_workflow_20251205_xyz789.jsonl")
```

## 输出示例

### Team 执行追踪

```
================================================================================
Trace Summary: abc12345
================================================================================

Duration: 45.23s
Total Events: 28

Event Counts:
  - workflow_start: 1
  - agent_start: 4
  - agent_end: 4
  - delegation: 3
  - tool_call: 15
  - workflow_end: 1

Agents:
  ✓ Leader (Leader_0)
      Steps: 12, Time: 25.5s
  ✓ Researcher (Researcher_1)
      Steps: 3, Time: 8.2s
  ✓ Writer (Writer_2)
      Steps: 2, Time: 6.1s
  ✓ Reviewer (Reviewer_3)
      Steps: 1, Time: 3.4s

Delegations:
  Leader → Researcher
  Leader → Writer
  Leader → Reviewer

================================================================================
Event Timeline
================================================================================

🚀 [2025-12-05T10:30:00] WORKFLOW START
   Type: team

👤 [2025-12-05T10:30:01] AGENT START
   Name: Leader
   Role: Team Leader
   Task: 研究 Python asyncio 并撰写技术文章

🔀 [2025-12-05T10:30:15] DELEGATION
   Leader → Researcher

  👤 [2025-12-05T10:30:15] AGENT START
     Name: Researcher
     Role: Research Specialist
     Task: 研究 Python asyncio 的核心概念

    ✓ [2025-12-05T10:30:23] AGENT END: Researcher
       Steps: 3, Time: 8.2s

🔀 [2025-12-05T10:30:30] DELEGATION
   Leader → Writer

  👤 [2025-12-05T10:30:30] AGENT START
     Name: Writer
     Role: Writing Expert
     Task: 撰写技术文章

    ✓ [2025-12-05T10:30:36] AGENT END: Writer
       Steps: 2, Time: 6.1s

   ✓ [2025-12-05T10:30:45] AGENT END: Leader
      Steps: 12, Time: 44.5s

🏁 [2025-12-05T10:30:45] WORKFLOW END
   Success: True
   Duration: 45.23s
```

### 依赖工作流追踪

```
================================================================================
Workflow Flow Visualization
================================================================================

Dependency Layers:
Layer 0: research
    ↓
Layer 1: analyze
    ↓
Layer 2: [write_doc || write_code]  (parallel)

================================================================================

📋 [2025-12-05T10:35:00] TASK START: research
   Layer: 0
   Assigned to: researcher
   Depends on: []

   ✓ [2025-12-05T10:35:08] TASK END: research
      Status: completed, Time: 8.2s

💬 [2025-12-05T10:35:08] MESSAGE PASS
   research → analyze

📋 [2025-12-05T10:35:08] TASK START: analyze
   Layer: 1
   Assigned to: analyst
   Depends on: ['research']

   ✓ [2025-12-05T10:35:14] TASK END: analyze
      Status: completed, Time: 6.0s

💬 [2025-12-05T10:35:14] MESSAGE PASS
   analyze → write_doc

💬 [2025-12-05T10:35:14] MESSAGE PASS
   analyze → write_code

📋 [2025-12-05T10:35:14] TASK START: write_doc
   Layer: 2
   Assigned to: writer
   Depends on: ['analyze']

📋 [2025-12-05T10:35:14] TASK START: write_code
   Layer: 2
   Assigned to: coder
   Depends on: ['analyze']

   ✓ [2025-12-05T10:35:20] TASK END: write_doc
      Status: completed, Time: 6.1s

   ✓ [2025-12-05T10:35:22] TASK END: write_code
      Status: completed, Time: 8.3s
```

## LangSmith vs 自建方案对比

### 何时使用自建方案（推荐）

✅ **适合场景**：
- 项目初期，快速验证功能
- 对数据隐私有严格要求
- 不想引入外部依赖
- 控制成本（零额外费用）
- 简单的调试和分析需求

✅ **优势**：
- 零成本
- 数据完全掌控
- 与现有架构无缝集成
- 灵活定制
- 离线可用

❌ **局限**：
- UI 是命令行，非图形化
- 需要自己实现高级分析功能
- 团队协作相对困难

### 何时考虑 LangSmith

✅ **适合场景**：
- 生产环境，需要专业监控
- 团队协作，多人分析日志
- 需要高级评估和对比功能
- 预算充足
- 与 LangChain 生态集成

✅ **优势**：
- 漂亮的 Web UI
- 自动追踪所有 LLM 调用
- 强大的搜索和分析
- 数据集管理和评估
- 团队协作功能

❌ **局限**：
- 需要付费（$39+/月）
- 数据上传到第三方
- 增加项目依赖
- 需要网络连接

### LangSmith 集成示例（可选）

```python
# 安装
pip install langsmith

# 在 .env 中配置
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_api_key
LANGCHAIN_PROJECT=fastapi-agent

# 在代码中启用
from langsmith import Client

client = Client()

# 自动追踪所有 LLM 调用
with client.trace(name="team_execution") as run:
    result = await team.run(message)
```

## 推荐使用策略

### 阶段 1: 开发期（当前）

使用**自建 TraceLogger**：
- 零成本快速迭代
- 完整掌控数据
- 满足基本调试需求

### 阶段 2: 生产前

评估是否需要 LangSmith：
- 如果团队 > 3人 → 考虑 LangSmith
- 如果需要高级分析 → 考虑 LangSmith
- 如果预算有限 → 继续自建方案

### 阶段 3: 生产环境

**混合使用**：
- 关键路径用 LangSmith 监控
- 普通请求用自建日志
- 定期导出 LangSmith 数据到本地

## 日志文件结构

```
~/.fastapi-agent/
├── log/                           # AgentLogger 输出
│   ├── agent_run_20251205_100000.log
│   └── agent_run_20251205_103000.log
└── traces/                        # TraceLogger 输出
    ├── trace_team_20251205_abc123.jsonl
    ├── trace_team_20251205_abc123.summary.json
    ├── trace_dependency_workflow_20251205_xyz789.jsonl
    └── trace_dependency_workflow_20251205_xyz789.summary.json
```

## 总结

**当前建议**：先实现 `TraceLogger`，满足基本需求：
1. ✅ 零成本
2. ✅ 完整追踪 Agent 流转
3. ✅ 可视化依赖工作流
4. ✅ 数据完全掌控

**未来考虑**：如果需要以下功能，再引入 LangSmith：
- 漂亮的 Web UI
- 团队协作和分享
- 高级评估和 A/B 测试
- 与 LangChain 生态深度集成
