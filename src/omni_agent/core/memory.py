"""统一 JSON 格式记忆存储系统"""

import json
import logging
import shutil
from datetime import datetime
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_str() -> str:
    return datetime.now().strftime(TIME_FORMAT)


def parse_time(time_str: str) -> datetime:
    try:
        return datetime.strptime(time_str, TIME_FORMAT)
    except (ValueError, TypeError):
        return datetime.now()


class MemoryType(str, Enum):
    """
    记忆类型
        SESSION: 会话记录 - 对话历史，按轮次存储
        PROFILE: 用户画像 - 持久化的用户信息（背景、技能、偏好）
        TASK: 当前任务 - 短期工作目标
        HABIT: 用户习惯 - 工作流程、操作模式
    """

    SESSION = "session"
    PROFILE = "profile"
    TASK = "task"
    HABIT = "habit"


@dataclass
class MemoryEntry:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    content: str = ""
    memory_type: str = "session"
    importance: float = 0.5
    timestamp: str = field(default_factory=now_str)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "type": self.memory_type,
            "importance": self.importance,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(
            id=data.get("id", uuid4().hex[:12]),
            content=data.get("content", ""),
            memory_type=data.get("type", "session"),
            importance=data.get("importance", 0.5),
            timestamp=data.get("timestamp", now_str()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class MemoryMeta:
    user_id: str = ""
    session_id: str = ""
    created_at: str = field(default_factory=now_str)
    updated_at: str = field(default_factory=now_str)


@dataclass
class MemoryContext:
    task: str = ""
    workspace: str = ""
    preferences: dict = field(default_factory=dict)


@dataclass
class MemorySummary:
    core_facts: list[str] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    last_compressed_at: float | None = None


class Memory:
    """JSON 格式的统一记忆存储

    目录结构:
        ./.agent_memories/{user_id}/{session_id}/memory.json
    """

    VERSION = "1.0"

    def __init__(
        self,
        user_id: str,
        session_id: str,
        base_dir: str = "./.agent_memories",
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.base_dir = Path(base_dir).expanduser()
        self.session_dir = self.base_dir / user_id / session_id
        self.path = self.session_dir / "memory.json"

        self._meta: MemoryMeta = MemoryMeta(user_id=user_id, session_id=session_id)
        self._context: MemoryContext = MemoryContext()
        self._memories: dict[str, list[dict]] = {
            "session": [],
            "profile": [],
            "task": [],
            "habit": [],
        }
        self._summary: MemorySummary = MemorySummary()

        self._ensure_dir()
        self._load()

    def _ensure_dir(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if not self.path.exists():
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._meta = MemoryMeta(**data.get("meta", {}))
            self._context = MemoryContext(**data.get("context", {}))
            self._memories = data.get("memories", self._memories)
            summary_data = data.get("summary", {})
            self._summary = MemorySummary(
                core_facts=summary_data.get("core_facts", []),
                decisions=summary_data.get("decisions", []),
                last_compressed_at=summary_data.get("last_compressed_at"),
            )
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to load memory: {e}")

    def _save(self) -> None:
        self._meta.updated_at = now_str()
        data = {
            "version": self.VERSION,
            "meta": asdict(self._meta),
            "context": asdict(self._context),
            "memories": self._memories,
            "summary": asdict(self._summary),
        }
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def exists(self) -> bool:
        return self.path.exists()

    def read(self) -> str:
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8")

    def delete(self) -> None:
        shutil.rmtree(self.session_dir, ignore_errors=True)

    def init_memory(self, context: str = "") -> dict:
        self._context.task = context
        self._save()
        return self.to_dict()

    def append_round(
        self,
        round_num: int,
        user_msg: str,
        assistant_msg: str,
        tools_used: list[str] | None = None,
    ) -> None:
        self.add_session(
            content=user_msg,
            role="user",
            round_num=round_num,
            importance=0.6,
        )
        self.add_session(
            content=assistant_msg,
            role="assistant",
            round_num=round_num,
            importance=0.5,
            tools_used=tools_used,
        )

    def add_session(
        self,
        content: str,
        role: str,
        round_num: int,
        importance: float = 0.5,
        tools_used: list[str] | None = None,
    ) -> str:
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.SESSION.value,
            importance=importance,
            metadata={
                "round": round_num,
                "role": role,
                "tools_used": tools_used or [],
            },
        )
        self._memories["session"].append(entry.to_dict())
        self._save()
        return entry.id

    def add_profile(
        self,
        content: str,
        source: str = "unknown",
        importance: float = 0.5,
        confidence: float = 1.0,
    ) -> str:
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.PROFILE.value,
            importance=importance,
            metadata={"source": source, "confidence": confidence},
        )
        self._memories["profile"].append(entry.to_dict())
        self._save()
        return entry.id

    def add_task(
        self,
        content: str,
        category: str = "general",
        status: str = "active",
        importance: float = 0.7,
    ) -> str:
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.TASK.value,
            importance=importance,
            metadata={"category": category, "status": status},
        )
        self._memories["task"].append(entry.to_dict())
        self._save()
        return entry.id

    def add_habit(
        self,
        content: str,
        skill_name: str,
        importance: float = 0.6,
    ) -> str:
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.HABIT.value,
            importance=importance,
            metadata={"skill_name": skill_name},
        )
        self._memories["habit"].append(entry.to_dict())
        self._save()
        return entry.id

    def update_context(
        self,
        task: str | None = None,
        workspace: str | None = None,
        preferences: dict | None = None,
    ) -> None:
        if task is not None:
            self._context.task = task
        if workspace is not None:
            self._context.workspace = workspace
        if preferences is not None:
            self._context.preferences.update(preferences)
        self._save()

    def update_core_facts(self, facts: list[str]) -> None:
        self._summary.core_facts = facts
        self._save()

    def add_core_fact(self, fact: str) -> None:
        if fact not in self._summary.core_facts:
            self._summary.core_facts.append(fact)
            self._save()

    def add_decision(self, decision: str, reason: str) -> None:
        self._summary.decisions.append({
            "decision": decision,
            "reason": reason,
            "timestamp": now_str(),
        })
        self._save()

    def update_task_status(self, entry_id: str, status: str) -> bool:
        for entry in self._memories["task"]:
            if entry.get("id") == entry_id:
                entry["metadata"]["status"] = status
                self._save()
                return True
        return False

    def get_memories(
        self,
        memory_type: MemoryType | None = None,
        min_importance: float = 0.0,
        limit: int = 50,
    ) -> list[dict]:
        if memory_type:
            memories = self._memories.get(memory_type.value, [])
        else:
            memories = []
            for mems in self._memories.values():
                memories.extend(mems)

        filtered = [m for m in memories if m.get("importance", 0) >= min_importance]
        sorted_mems = sorted(filtered, key=lambda x: x.get("timestamp", 0), reverse=True)
        return sorted_mems[:limit]

    def get_recent_session(self, n: int = 5) -> list[dict]:
        return self._memories["session"][-n:]

    def get_task_by_category(self, category: str) -> list[dict]:
        return [
            m
            for m in self._memories["task"]
            if m.get("metadata", {}).get("category") == category
        ]

    def get_pending_tasks(self) -> list[dict]:
        return [
            m
            for m in self._memories["task"]
            if m.get("metadata", {}).get("category") == "todo"
            and m.get("metadata", {}).get("status") != "completed"
        ]

    def get_context_for_prompt(self) -> str:
        data = {
            "user_profile": [m.get("content") for m in self._memories.get("profile", [])],
            "user_habits": [m.get("content") for m in self._memories.get("habit", [])],
            "current_tasks": [m.get("content") for m in self._memories.get("task", []) 
                             if m.get("metadata", {}).get("status") != "completed"],
            "recent_conversation": [
                {"role": m.get("metadata", {}).get("role"), "content": m.get("content")}
                for m in self.get_recent_session(3)
            ],
        }
        
        if not any(data.values()):
            return ""
        
        lines = ["<user_memory>"]
        
        if data["user_profile"]:
            lines.append("用户画像:")
            for p in data["user_profile"]:
                lines.append(f"  - {p}")
        
        if data["user_habits"]:
            lines.append("用户习惯:")
            for h in data["user_habits"]:
                lines.append(f"  - {h}")
        
        if data["current_tasks"]:
            lines.append("当前任务:")
            for t in data["current_tasks"]:
                lines.append(f"  - {t}")

        if data["recent_conversation"]:
            lines.append("最近对话摘要:")
            for conv in data["recent_conversation"][-3:]:
                role = "用户" if conv["role"] == "user" else "助手"
                content = conv["content"][:80] if conv["content"] else ""
                if content:
                    lines.append(f"  {role}: {content}...")

        lines.append("</user_memory>")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "version": self.VERSION,
            "meta": asdict(self._meta),
            "context": asdict(self._context),
            "memories": self._memories,
            "summary": asdict(self._summary),
        }

    def clear_session(self) -> None:
        self._memories["session"] = []
        self._save()

    def clear_task(self) -> None:
        self._memories["task"] = []
        self._save()

    def clear_all(self) -> None:
        self._memories = {
            "session": [],
            "profile": [],
            "task": [],
            "habit": [],
        }
        self._summary = MemorySummary()
        self._save()

    def compress(
        self,
        max_profile: int = 3,
        max_task: int = 5,
        max_session: int = 6,
        max_habit: int = 3,
    ) -> dict[str, int]:
        """压缩记忆，去除重复和过期内容。

        Args:
            max_profile: 保留的最大 profile 数量
            max_task: 保留的最大 active task 数量
            max_session: 保留的最大 session 数量（建议为偶数，对应对话轮数）
            max_habit: 保留的最大 habit 数量

        Returns:
            各类型压缩前后的数量变化
        """
        stats = {}

        before = len(self._memories["profile"])
        self._memories["profile"] = self._memories["profile"][-max_profile:]
        stats["profile"] = before - len(self._memories["profile"])

        before = len(self._memories["task"])
        active_tasks = [
            t for t in self._memories["task"]
            if t.get("metadata", {}).get("status") != "completed"
        ]
        self._memories["task"] = active_tasks[-max_task:]
        stats["task"] = before - len(self._memories["task"])

        before = len(self._memories["session"])
        self._memories["session"] = self._memories["session"][-max_session:]
        stats["session"] = before - len(self._memories["session"])

        before = len(self._memories["habit"])
        self._memories["habit"] = self._memories["habit"][-max_habit:]
        stats["habit"] = before - len(self._memories["habit"])

        import time
        self._summary.last_compressed_at = time.time()
        self._save()

        total_removed = sum(stats.values())
        if total_removed > 0:
            logger.info(f"Memory compressed: removed {total_removed} items {stats}")

        return stats

    def needs_compression(
        self,
        threshold_profile: int = 5,
        threshold_task: int = 8,
        threshold_session: int = 10,
    ) -> bool:
        """检查是否需要压缩。"""
        return (
            len(self._memories["profile"]) > threshold_profile
            or len(self._memories["task"]) > threshold_task
            or len(self._memories["session"]) > threshold_session
        )

    @property
    def meta(self) -> MemoryMeta:
        return self._meta

    @property
    def context(self) -> MemoryContext:
        return self._context

    @property
    def summary(self) -> MemorySummary:
        return self._summary

    @property
    def session_count(self) -> int:
        return len(self._memories["session"])

    @property
    def total_count(self) -> int:
        return sum(len(mems) for mems in self._memories.values())


class MemoryManager:
    """记忆管理器，管理多个用户/会话的记忆"""

    def __init__(self, base_dir: str = "./.agent_memories"):
        self.base_dir = Path(base_dir).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_memory(self, user_id: str, session_id: str) -> Memory:
        return Memory(user_id, session_id, str(self.base_dir))

    def delete_session(self, user_id: str, session_id: str) -> bool:
        session_dir = self.base_dir / user_id / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)
            return True
        return False

    def delete_user(self, user_id: str) -> bool:
        user_dir = self.base_dir / user_id
        if user_dir.exists():
            shutil.rmtree(user_dir)
            return True
        return False

    def list_sessions(self, user_id: str) -> list[str]:
        user_dir = self.base_dir / user_id
        if not user_dir.exists():
            return []
        return [d.name for d in user_dir.iterdir() if d.is_dir()]

    def list_users(self) -> list[str]:
        if not self.base_dir.exists():
            return []
        return [d.name for d in self.base_dir.iterdir() if d.is_dir()]

    def cleanup_expired(self, max_age_days: int = 30) -> int:
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0

        for user_id in self.list_users():
            for session_id in self.list_sessions(user_id):
                memory = self.get_memory(user_id, session_id)
                if memory.exists():
                    updated = parse_time(memory.meta.updated_at)
                    if updated < cutoff:
                        memory.delete()
                        removed += 1

        return removed

    def get_stats(self) -> dict:
        users = self.list_users()
        total_sessions = 0
        total_memories = 0

        for user_id in users:
            sessions = self.list_sessions(user_id)
            total_sessions += len(sessions)
            for session_id in sessions:
                memory = self.get_memory(user_id, session_id)
                total_memories += memory.total_count

        return {
            "users": len(users),
            "sessions": total_sessions,
            "memories": total_memories,
        }
