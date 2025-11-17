# Team 会话管理 - 基于 agno 的优化方案

## agno TeamSession 核心功能分析

### 1. 数据结构

```python
@dataclass
class TeamSession:
    session_id: str                      # 会话 ID
    team_id: Optional[str]               # Team ID
    user_id: Optional[str]               # 用户 ID
    
    team_data: Optional[Dict]            # Team 元数据
    session_data: Optional[Dict]         # 会话数据 (state, media)
    metadata: Optional[Dict]             # 自定义元数据
    
    runs: List[Union[TeamRunOutput, RunOutput]]  # 所有运行记录
    summary: Optional[SessionSummary]     # 会话摘要
    
    created_at: int
    updated_at: int
```

**关键特性:**
- ✅ 存储所有 runs (包括 team leader 和 member runs)
- ✅ 区分父子 run (`parent_run_id`)
- ✅ 支持会话状态 (`session_data`)
- ✅ 支持会话摘要

### 2. 核心方法

#### `upsert_run(run_response)`
添加或更新 run 记录:
```python
def upsert_run(self, run_response):
    """Adds a RunOutput to the runs list."""
    if not self.runs:
        self.runs = []
    
    # 检查是否已存在,存在则更新
    for i, existing_run in enumerate(self.runs):
        if existing_run.run_id == run_response.run_id:
            self.runs[i] = run_response
            break
    else:
        self.runs.append(run_response)
```

#### `get_messages_from_last_n_runs()`
获取最近 n 次运行的消息:
```python
def get_messages_from_last_n_runs(
    self,
    agent_id: Optional[str] = None,
    team_id: Optional[str] = None,
    last_n: Optional[int] = None,
    skip_history_messages: bool = True,
    member_runs: bool = False,  # 是否包含成员 runs
) -> List[Message]:
    # 1. 过滤 runs (by agent_id, team_id)
    # 2. 过滤父子 run (member_runs=False 只要顶层 runs)
    # 3. 过滤状态 (skip paused, cancelled, error)
    # 4. 提取消息
    # 5. 去重和清理
    return messages
```

#### `get_team_history_context(num_runs)`
获取格式化的团队历史上下文:
```python
def get_team_history_context(self, num_runs=None) -> str:
    """格式化历史记录用于注入 leader 系统提示."""
    history_data = self.get_team_history(num_runs)
    
    context = "<team_history_context>\n"
    for i, (input_str, response_str) in enumerate(history_data):
        context += f"[run-{i+1}]\n"
        context += f"input: {input_str}\n"
        context += f"response: {response_str}\n\n"
    context += "</team_history_context>"
    
    return context
```

**用于:**
- Team leader 在新一轮运行时了解之前的上下文
- 保持多轮对话的连贯性

### 3. 会话历史的使用

在 Team 运行时:
```python
# 1. 获取历史上下文
if self.add_team_history_to_members and session:
    team_history_str = session.get_team_history_context(
        num_runs=self.num_team_history_runs
    )

# 2. 添加到成员任务描述
member_agent_task = format_member_agent_task(
    task_description=task_description,
    team_history_str=team_history_str,  # 注入历史
)

# 3. 成员运行后保存
session.upsert_run(member_agent_run_response)
```

## 本项目的优化设计

### 核心需求

1. **多轮对话支持** - Team 需要记住之前的交互
2. **成员运行追踪** - 记录哪个成员执行了什么任务
3. **上下文注入** - 将历史记录注入到新的运行中
4. **轻量实现** - 不需要完整的数据库支持

### 设计方案

```
┌─────────────────────────────────────────────┐
│          TeamSessionManager                 │
│  - 管理所有会话                              │
│  - 内存存储 + 可选持久化                     │
└─────────────────┬───────────────────────────┘
                  │
     ┌────────────┴────────────┐
     │                         │
┌────▼──────┐         ┌────────▼────────┐
│TeamSession│         │TeamSession      │
│session_id │         │session_id       │
│           │         │                 │
│runs: []   │         │runs: []         │
│state: {}  │         │state: {}        │
└───────────┘         └─────────────────┘
```

### 数据模型

```python
@dataclass
class RunRecord:
    """单次运行记录."""
    
    run_id: str
    parent_run_id: Optional[str]  # 父 run ID (成员 run 才有)
    
    # 运行者信息
    runner_type: str  # "team_leader" 或 "member"
    runner_name: str  # Team/Member 名称
    
    # 任务和响应
    task: str
    response: str
    success: bool
    
    # 元数据
    steps: int
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class TeamSession:
    """Team 会话."""
    
    session_id: str
    team_name: str
    user_id: Optional[str]
    
    # 运行记录
    runs: List[RunRecord]
    
    # 会话状态
    state: Dict[str, Any]
    
    # 时间戳
    created_at: float
    updated_at: float
    
    def add_run(self, run: RunRecord):
        """添加运行记录."""
        self.runs.append(run)
        self.updated_at = time.time()
    
    def get_history_context(self, num_runs: int = 3) -> str:
        """获取历史上下文 (仅 leader runs)."""
        leader_runs = [r for r in self.runs if r.runner_type == "team_leader"]
        recent_runs = leader_runs[-num_runs:] if num_runs else leader_runs
        
        if not recent_runs:
            return ""
        
        context = "<team_history>\n"
        for i, run in enumerate(recent_runs, 1):
            context += f"[Round {i}]\n"
            context += f"Task: {run.task}\n"
            context += f"Response: {run.response}\n\n"
        context += "</team_history>"
        
        return context
    
    def get_member_interactions(self, current_run_id: str) -> str:
        """获取当前运行的成员交互."""
        member_runs = [
            r for r in self.runs 
            if r.parent_run_id == current_run_id
        ]
        
        if not member_runs:
            return ""
        
        context = "<member_interactions>\n"
        for run in member_runs:
            context += f"{run.runner_name}:\n"
            context += f"  Task: {run.task}\n"
            context += f"  Response: {run.response}\n\n"
        context += "</member_interactions>"
        
        return context


class TeamSessionManager:
    """Team 会话管理器."""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.sessions: Dict[str, TeamSession] = {}
        self.storage_path = storage_path
        
        # 可选: 从文件加载
        if storage_path:
            self._load_from_storage()
    
    def get_session(
        self,
        session_id: str,
        team_name: str,
        user_id: Optional[str] = None
    ) -> TeamSession:
        """获取或创建会话."""
        if session_id not in self.sessions:
            self.sessions[session_id] = TeamSession(
                session_id=session_id,
                team_name=team_name,
                user_id=user_id,
                runs=[],
                state={},
                created_at=time.time(),
                updated_at=time.time(),
            )
        return self.sessions[session_id]
    
    def add_run(
        self,
        session_id: str,
        run: RunRecord
    ):
        """添加运行记录."""
        if session_id in self.sessions:
            self.sessions[session_id].add_run(run)
            
            # 可选: 保存到文件
            if self.storage_path:
                self._save_to_storage()
    
    def _save_to_storage(self):
        """保存到文件."""
        if not self.storage_path:
            return
        
        import json
        from dataclasses import asdict
        
        data = {
            session_id: asdict(session)
            for session_id, session in self.sessions.items()
        }
        
        Path(self.storage_path).write_text(
            json.dumps(data, indent=2)
        )
    
    def _load_from_storage(self):
        """从文件加载."""
        if not self.storage_path or not Path(self.storage_path).exists():
            return
        
        import json
        from typing import cast
        
        data = json.loads(Path(self.storage_path).read_text())
        
        for session_id, session_data in data.items():
            # 重建 RunRecord 对象
            runs = [
                RunRecord(**run_data) 
                for run_data in session_data["runs"]
            ]
            
            self.sessions[session_id] = TeamSession(
                session_id=session_data["session_id"],
                team_name=session_data["team_name"],
                user_id=session_data.get("user_id"),
                runs=runs,
                state=session_data.get("state", {}),
                created_at=session_data["created_at"],
                updated_at=session_data["updated_at"],
            )
```

## 集成到 Team 类

```python
class Team:
    def __init__(
        self,
        config: TeamConfig,
        llm_client: LLMClient,
        session_manager: Optional[TeamSessionManager] = None,
        **kwargs
    ):
        self.config = config
        self.llm_client = llm_client
        self.session_manager = session_manager or TeamSessionManager()
    
    def run(
        self,
        message: str,
        session_id: str = "default",
        user_id: Optional[str] = None,
        max_steps: int = 50
    ) -> TeamRunResponse:
        """运行团队 (支持会话)."""
        import uuid
        from time import time
        
        # 1. 获取会话
        session = self.session_manager.get_session(
            session_id=session_id,
            team_name=self.config.name,
            user_id=user_id
        )
        
        # 2. 获取历史上下文
        history_context = session.get_history_context(num_runs=3)
        
        # 3. 构建 leader 提示 (包含历史)
        leader_prompt = self._build_leader_prompt_with_history(
            message=message,
            history_context=history_context
        )
        
        # 4. 创建当前 run ID
        current_run_id = str(uuid.uuid4())
        
        # 5. 运行 leader (会调用成员)
        response = self._run_leader(
            leader_prompt,
            current_run_id=current_run_id,
            session=session
        )
        
        # 6. 保存 leader run
        leader_run = RunRecord(
            run_id=current_run_id,
            parent_run_id=None,
            runner_type="team_leader",
            runner_name=self.config.name,
            task=message,
            response=response.message,
            success=response.success,
            steps=response.total_steps,
            timestamp=time(),
            metadata=response.metadata
        )
        
        self.session_manager.add_run(session_id, leader_run)
        
        return response
    
    def _run_member(
        self,
        member_config: TeamMemberConfig,
        task: str,
        current_run_id: str,
        session: TeamSession
    ) -> MemberRunResult:
        """运行成员 (记录到会话)."""
        import uuid
        from time import time
        
        # 1. 运行成员
        result = self._execute_member(member_config, task)
        
        # 2. 保存成员 run
        member_run = RunRecord(
            run_id=str(uuid.uuid4()),
            parent_run_id=current_run_id,  # 关联到 leader run
            runner_type="member",
            runner_name=member_config.name,
            task=task,
            response=result.response,
            success=result.success,
            steps=result.steps,
            timestamp=time(),
            metadata=result.metadata
        )
        
        self.session_manager.add_run(session.session_id, member_run)
        
        return result
```

## 使用示例

### 示例 1: 多轮对话

```python
from fastapi_agent.core.team import Team, TeamSessionManager
from fastapi_agent.schemas.team import TeamConfig, TeamMemberConfig

# 创建会话管理器
session_manager = TeamSessionManager(
    storage_path="~/.team_sessions.json"  # 可选持久化
)

# 创建团队
team = Team(
    config=TeamConfig(
        name="Research Team",
        members=[
            TeamMemberConfig(name="Researcher", role="Research"),
            TeamMemberConfig(name="Writer", role="Writing"),
        ]
    ),
    llm_client=llm_client,
    session_manager=session_manager,  # 传入会话管理器
)

# 第一轮对话
response1 = team.run(
    message="Research Python asyncio",
    session_id="user-123",  # 指定会话 ID
)
print(response1.message)

# 第二轮对话 (有历史上下文)
response2 = team.run(
    message="Now write a tutorial based on that research",
    session_id="user-123",  # 同一个会话
)
# Leader 能看到上一轮的研究结果!
print(response2.message)

# 查看会话历史
session = session_manager.get_session("user-123", "Research Team")
print(f"Total runs: {len(session.runs)}")
print(session.get_history_context())
```

### 示例 2: 会话状态

```python
# 在会话中保存状态
session = session_manager.get_session("user-123", "Research Team")
session.state["topic"] = "asyncio"
session.state["progress"] = "research_done"

# 下次运行时可以访问
if session.state.get("progress") == "research_done":
    print("Research already completed, proceeding to writing...")
```

## 优化对比

| 特性 | agno | 本实现 | 说明 |
|------|------|--------|------|
| 会话存储 | ✅ Database | ✅ Memory + File | 轻量化 |
| Run 记录 | ✅ | ✅ | 完整记录 |
| 父子 Run | ✅ | ✅ | parent_run_id |
| 历史上下文 | ✅ | ✅ | get_history_context |
| 会话状态 | ✅ | ✅ | state dict |
| 会话摘要 | ✅ | ❌ | 可后续添加 |
| 过滤查询 | ✅ 复杂 | ✅ 简化 | 够用即可 |

## 实施计划

### Phase 1: 核心功能 (优先)
- [x] RunRecord 数据模型
- [x] TeamSession 类
- [x] TeamSessionManager 类
- [ ] 集成到 Team.run()

### Phase 2: 增强功能
- [ ] 文件持久化
- [ ] 会话清理 (过期会话)
- [ ] 会话摘要
- [ ] 更多查询选项

### Phase 3: 高级功能
- [ ] 数据库支持 (可选)
- [ ] 会话分析
- [ ] 导出/导入

## 总结

通过借鉴 agno 的 TeamSession 实现,我们为本项目设计了一个轻量但实用的会话管理系统:

1. ✅ **完整记录** - 所有 runs (leader + members)
2. ✅ **历史上下文** - 注入到新运行
3. ✅ **会话状态** - 保持状态
4. ✅ **简化实现** - 不需要数据库
5. ✅ **可扩展** - 易于添加新功能

这将显著提升 Team 的多轮对话能力! 🚀
