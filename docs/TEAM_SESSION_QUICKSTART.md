# Team 会话管理 - 快速开始

## 🚀 5 分钟上手

### 基础使用 (无会话)

```python
from omni_agent.core.llm_client import LLMClient
from omni_agent.core.team import Team
from omni_agent.schemas.team import TeamConfig, TeamMemberConfig

# 创建团队配置
team_config = TeamConfig(
    name="Research Team",
    members=[
        TeamMemberConfig(name="Researcher", role="Research Specialist"),
        TeamMemberConfig(name="Writer", role="Technical Writer"),
    ],
)

# 创建 Team
team = Team(
    config=team_config,
    llm_client=llm_client,
    available_tools=[...],
)

# 运行任务 (无会话记录)
response = team.run("Research Python asyncio")
print(response.message)
```

### 多轮对话 (有会话)

```python
from omni_agent.core.session import TeamSessionManager

# 创建会话管理器
session_manager = TeamSessionManager(
    storage_path="~/.omni-agent/team_sessions.json"  # 可选持久化
)

# 创建 Team (传入 session_manager)
team = Team(
    config=team_config,
    llm_client=llm_client,
    session_manager=session_manager,  # 启用会话管理
)

# 第一轮对话
response1 = team.run(
    message="Research Python asyncio",
    session_id="user-123",  # 指定会话 ID
)

# 第二轮对话 (自动包含历史上下文)
response2 = team.run(
    message="Based on that research, write a tutorial",
    session_id="user-123",  # 同一个会话
)
# Leader 能看到上一轮的研究结果!
```

## 📋 核心概念

### 1. 会话管理器 (TeamSessionManager)

```python
session_manager = TeamSessionManager(
    storage_path="path/to/sessions.json"  # 可选,启用文件持久化
)
```

**特性:**
- ✅ 内存存储 + 可选文件持久化
- ✅ 自动加载已有会话
- ✅ 支持多个会话并存

### 2. 会话 (TeamSession)

每个会话包含:
- `session_id`: 会话唯一标识
- `runs`: 所有运行记录 (leader + members)
- `state`: 自定义状态字典
- `created_at`, `updated_at`: 时间戳

### 3. 运行记录 (RunRecord)

每条记录包含:
- `run_id`: 运行 ID
- `parent_run_id`: 父运行 ID (member run 才有)
- `runner_type`: "team_leader" 或 "member"
- `task`, `response`: 任务和响应
- `success`, `steps`: 执行结果

## 🎯 使用场景

### 场景 1: 多轮研究和写作

```python
# 第 1 轮: 研究
team.run("Research topic X", session_id="project-A")

# 第 2 轮: 基于研究写作 (有上下文)
team.run("Write a report based on research", session_id="project-A")

# 第 3 轮: 补充内容 (继续上下文)
team.run("Add code examples to the report", session_id="project-A")
```

### 场景 2: 用户专属会话

```python
# 用户 A 的会话
team.run("Help me with task 1", session_id="user-alice", user_id="alice")
team.run("Continue with task 2", session_id="user-alice")

# 用户 B 的会话 (完全独立)
team.run("Different task", session_id="user-bob", user_id="bob")
```

### 场景 3: 检查会话历史

```python
# 获取会话
session = session_manager.get_session("user-123", "Research Team")

# 查看统计
stats = session.get_runs_count()
print(f"Total runs: {stats['total']}")
print(f"Leader runs: {stats['leader']}")
print(f"Member runs: {stats['member']}")

# 查看历史上下文
history = session.get_history_context(num_runs=3)
print(history)

# 查看所有运行
for run in session.runs:
    print(f"[{run.runner_type}] {run.runner_name}: {run.task}")
```

## 📊 API 参考

### Team.run() 参数

```python
team.run(
    message: str,              # 必需: 任务描述
    max_steps: int = 50,       # 最大执行步数
    session_id: str = None,    # 可选: 会话 ID
    user_id: str = None,       # 可选: 用户 ID
    num_history_runs: int = 3  # 历史上下文包含的运行数
)
```

### TeamSessionManager 方法

```python
# 获取或创建会话
session = manager.get_session(session_id, team_name, user_id)

# 添加运行记录
manager.add_run(session_id, run_record)

# 获取所有会话
all_sessions = manager.get_all_sessions()

# 删除会话
manager.delete_session(session_id)

# 清空所有会话
manager.clear_all_sessions()
```

### TeamSession 方法

```python
# 获取历史上下文
context = session.get_history_context(num_runs=3)

# 获取成员交互记录
interactions = session.get_member_interactions(current_run_id)

# 获取运行统计
stats = session.get_runs_count()

# 添加运行
session.add_run(run_record)
```

## 💡 最佳实践

### 1. 会话 ID 命名

```python
# ✅ 推荐: 有意义的命名
session_id = "user-123"
session_id = "project-alpha"
session_id = f"task-{task_id}"

# ❌ 不推荐: 随机 UUID (难以追踪)
session_id = "550e8400-e29b-41d4-a716-446655440000"
```

### 2. 持久化路径

```python
# ✅ 推荐: 用户目录
storage_path = "~/.omni-agent/team_sessions.json"

# ✅ 推荐: 项目目录
storage_path = "./data/sessions.json"

# ❌ 避免: 临时目录 (可能被清理)
storage_path = "/tmp/sessions.json"
```

### 3. 历史上下文数量

```python
# ✅ 推荐: 3-5 轮 (平衡上下文和性能)
num_history_runs = 3

# ⚠️ 谨慎: 太多轮可能超出 token 限制
num_history_runs = 20  # 可能导致上下文过长
```

### 4. 会话清理

```python
# 定期清理过期会话
import time
from pathlib import Path

def cleanup_old_sessions(manager, max_age_days=30):
    """清理超过指定天数的会话."""
    cutoff = time.time() - (max_age_days * 24 * 3600)

    for session_id, session in list(manager.sessions.items()):
        if session.updated_at < cutoff:
            manager.delete_session(session_id)
            print(f"Deleted old session: {session_id}")
```

## 🔧 高级用法

### 自定义会话状态

```python
# 获取会话
session = session_manager.get_session("user-123", "Research Team")

# 保存自定义状态
session.state["current_topic"] = "Python asyncio"
session.state["progress"] = "research_done"
session.state["files"] = ["report.md", "code.py"]

# 下次运行时访问
if session.state.get("progress") == "research_done":
    print("Research already done, proceeding to writing...")
```

### 父子运行追踪

```python
# Leader run 的 parent_run_id 为 None
# Member run 的 parent_run_id 指向其 leader run

for run in session.runs:
    if run.parent_run_id is None:
        print(f"Leader run: {run.task}")
    else:
        print(f"  └─ Member run: {run.runner_name} - {run.task}")
```

### 导出会话数据

```python
import json
from dataclasses import asdict

# 获取会话
session = session_manager.get_session("user-123", "Research Team")

# 转换为字典
session_dict = {
    "session_id": session.session_id,
    "team_name": session.team_name,
    "runs": [asdict(run) for run in session.runs],
    "state": session.state,
    "created_at": session.created_at,
    "updated_at": session.updated_at,
}

# 导出为 JSON
with open("session_export.json", "w") as f:
    json.dump(session_dict, f, indent=2)
```

## ❓ 常见问题

**Q: 必须使用会话管理吗?**
A: 不是必须。不传 `session_id` 参数时,Team 正常运行,只是没有历史记录。

**Q: 会话数据存在哪里?**
A: 默认在内存中。如果传 `storage_path` 参数,会自动保存到 JSON 文件。

**Q: 如何实现跨进程共享会话?**
A: 使用文件持久化 (`storage_path`),不同进程加载同一文件即可。

**Q: 会话文件会自动清理吗?**
A: 不会自动清理,需要手动调用 `delete_session()` 或定期清理脚本。

**Q: 历史上下文如何注入?**
A: 自动注入到 leader 的系统提示末尾,使用 `<team_history>` XML 标签包裹。

**Q: 成员的运行记录会保存吗?**
A: 会!所有 leader 和 member 的运行都会被记录,并通过 `parent_run_id` 建立关系。

## 📚 更多资源

- 完整设计文档: `docs/TEAM_SESSION_MANAGEMENT.md`
- 测试示例: `examples/test_team_session.py`
- API 文档: `src/omni_agent/core/session.py`

## ✨ 总结

使用 Team 会话管理,你可以:

1. ✅ **多轮对话** - 保持上下文连贯性
2. ✅ **历史追踪** - 完整记录所有运行
3. ✅ **父子关系** - 追踪 leader 和 member 的交互
4. ✅ **可选持久化** - 支持文件存储
5. ✅ **灵活配置** - 按需启用,向后兼容

立即开始使用,让你的 Team 支持多轮对话! 🚀
