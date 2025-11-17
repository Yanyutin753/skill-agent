"""
Team 会话管理系统

提供轻量级的会话记录和历史上下文管理,参考 agno 的 TeamSession 实现。
"""

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RunRecord:
    """单次运行记录.

    记录 Team leader 或 member 的单次运行结果,支持父子关系追踪。
    """

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
    """Team 会话.

    管理单个会话的所有运行记录和状态。
    """

    session_id: str
    team_name: str
    user_id: Optional[str]

    # 运行记录
    runs: List[RunRecord]

    # 会话状态 (可用于存储自定义数据)
    state: Dict[str, Any]

    # 时间戳
    created_at: float
    updated_at: float

    def add_run(self, run: RunRecord) -> None:
        """添加运行记录."""
        self.runs.append(run)
        self.updated_at = time.time()

    def get_history_context(self, num_runs: Optional[int] = 3) -> str:
        """获取历史上下文 (仅 leader runs).

        Args:
            num_runs: 返回最近 N 轮运行,None 表示全部

        Returns:
            格式化的历史上下文,使用 XML 标签包裹
        """
        # 筛选 leader runs
        leader_runs = [r for r in self.runs if r.runner_type == "team_leader"]

        # 获取最近 N 轮
        if num_runs is not None:
            recent_runs = leader_runs[-num_runs:] if leader_runs else []
        else:
            recent_runs = leader_runs

        if not recent_runs:
            return ""

        # 构建上下文
        context = "<team_history>\n"
        for i, run in enumerate(recent_runs, 1):
            context += f"[Round {i}]\n"
            context += f"Task: {run.task}\n"
            context += f"Response: {run.response}\n\n"
        context += "</team_history>"

        return context

    def get_member_interactions(self, current_run_id: str) -> str:
        """获取当前运行的成员交互历史.

        Args:
            current_run_id: 当前 leader run ID

        Returns:
            格式化的成员交互记录
        """
        # 筛选当前 run 的子 runs
        member_runs = [
            r for r in self.runs
            if r.parent_run_id == current_run_id
        ]

        if not member_runs:
            return ""

        # 构建上下文
        context = "<member_interactions>\n"
        for run in member_runs:
            context += f"{run.runner_name}:\n"
            context += f"  Task: {run.task}\n"
            context += f"  Response: {run.response}\n\n"
        context += "</member_interactions>"

        return context

    def get_runs_count(self) -> Dict[str, int]:
        """获取运行统计.

        Returns:
            包含各类运行计数的字典
        """
        leader_count = sum(1 for r in self.runs if r.runner_type == "team_leader")
        member_count = sum(1 for r in self.runs if r.runner_type == "member")

        return {
            "total": len(self.runs),
            "leader": leader_count,
            "member": member_count,
        }


class TeamSessionManager:
    """Team 会话管理器.

    管理所有会话的生命周期,支持内存存储和可选的文件持久化。
    """

    def __init__(self, storage_path: Optional[str] = None):
        """初始化会话管理器.

        Args:
            storage_path: 可选的持久化存储路径,None 表示仅内存存储
        """
        self.sessions: Dict[str, TeamSession] = {}
        self.storage_path = storage_path

        # 如果指定了存储路径,尝试加载已有会话
        if storage_path:
            self._load_from_storage()

    def get_session(
        self,
        session_id: str,
        team_name: str,
        user_id: Optional[str] = None
    ) -> TeamSession:
        """获取或创建会话.

        Args:
            session_id: 会话 ID
            team_name: Team 名称
            user_id: 可选的用户 ID

        Returns:
            TeamSession 实例
        """
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
    ) -> None:
        """添加运行记录到会话.

        Args:
            session_id: 会话 ID
            run: 运行记录
        """
        if session_id in self.sessions:
            self.sessions[session_id].add_run(run)

            # 可选: 保存到文件
            if self.storage_path:
                self._save_to_storage()

    def get_all_sessions(self) -> Dict[str, TeamSession]:
        """获取所有会话.

        Returns:
            会话字典 {session_id: TeamSession}
        """
        return self.sessions

    def delete_session(self, session_id: str) -> bool:
        """删除会话.

        Args:
            session_id: 会话 ID

        Returns:
            删除是否成功
        """
        if session_id in self.sessions:
            del self.sessions[session_id]

            # 更新存储
            if self.storage_path:
                self._save_to_storage()

            return True
        return False

    def clear_all_sessions(self) -> None:
        """清空所有会话."""
        self.sessions.clear()

        # 清空存储文件
        if self.storage_path:
            self._save_to_storage()

    def _save_to_storage(self) -> None:
        """保存到文件."""
        if not self.storage_path:
            return

        # 转换为可序列化的字典
        data = {}
        for session_id, session in self.sessions.items():
            # 转换 runs
            runs_data = [asdict(run) for run in session.runs]

            data[session_id] = {
                "session_id": session.session_id,
                "team_name": session.team_name,
                "user_id": session.user_id,
                "runs": runs_data,
                "state": session.state,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }

        # 写入文件
        storage_file = Path(self.storage_path).expanduser()
        storage_file.parent.mkdir(parents=True, exist_ok=True)

        with storage_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_from_storage(self) -> None:
        """从文件加载."""
        if not self.storage_path:
            return

        storage_file = Path(self.storage_path).expanduser()

        if not storage_file.exists():
            return

        try:
            with storage_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # 重建会话对象
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
        except (json.JSONDecodeError, KeyError) as e:
            # 如果文件损坏,记录错误但继续运行
            print(f"Warning: Failed to load sessions from {self.storage_path}: {e}")
            self.sessions = {}
