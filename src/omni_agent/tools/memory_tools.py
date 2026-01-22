"""Memory Tools - 让 Agent 自主管理不同类型的记忆

提供工具让 Agent 在执行过程中：
- 存储语义记忆（长期知识、用户偏好）
- 存储工作记忆（待办、进度、决策、错误）
- 更新任务状态
- 查询历史记忆
- 记录重要决策
"""

from typing import Any

from omni_agent.core.memory import Memory, MemoryType
from omni_agent.tools.base import Tool, ToolResult


class StoreSemanticMemoryTool(Tool):
    """存储语义记忆 - 长期知识和事实"""

    def __init__(self, memory: Memory):
        self._memory = memory

    @property
    def name(self) -> str:
        return "store_semantic_memory"

    @property
    def description(self) -> str:
        return (
            "存储长期有效的知识或事实到语义记忆。"
            "适用于：用户偏好、项目信息、技术栈、重要发现等。"
            "这些信息会跨会话保留，用于建立长期上下文。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要记忆的知识或事实，简洁明确",
                },
                "source": {
                    "type": "string",
                    "description": "信息来源：user_stated（用户明确说的）、inferred（推断的）、codebase（代码分析）、conversation（对话中发现）",
                    "enum": ["user_stated", "inferred", "codebase", "conversation"],
                },
                "importance": {
                    "type": "number",
                    "description": "重要性 0-1，默认 0.5。用户明确偏好应该更高。",
                    "minimum": 0,
                    "maximum": 1,
                },
            },
            "required": ["content", "source"],
        }

    async def execute(
        self,
        content: str,
        source: str,
        importance: float = 0.5,
    ) -> ToolResult:
        try:
            entry_id = self._memory.add_profile(
                content=content,
                source=source,
                importance=importance,
            )
            return ToolResult(
                success=True,
                content=f"已存储语义记忆 [{entry_id}]: {content}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"存储语义记忆失败: {e}",
            )


class StoreWorkingMemoryTool(Tool):
    """存储工作记忆 - 当前任务相关信息"""

    def __init__(self, memory: Memory):
        self._memory = memory

    @property
    def name(self) -> str:
        return "store_working_memory"

    @property
    def description(self) -> str:
        return (
            "存储当前任务相关的工作记忆。"
            "category 类型：\n"
            "- todo: 待办事项，需要完成的任务\n"
            "- progress: 进度记录，已完成的步骤\n"
            "- finding: 发现/洞察，执行过程中的发现\n"
            "- error: 错误记录，遇到的问题"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "记忆内容",
                },
                "category": {
                    "type": "string",
                    "description": "记忆分类",
                    "enum": ["todo", "progress", "finding", "error"],
                },
            },
            "required": ["content", "category"],
        }

    async def execute(
        self,
        content: str,
        category: str,
    ) -> ToolResult:
        try:
            status = "pending" if category == "todo" else "active"
            entry_id = self._memory.add_task(
                content=content,
                category=category,
                status=status,
            )
            return ToolResult(
                success=True,
                content=f"已存储工作记忆 [{category}]: {content} (id: {entry_id})",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"存储工作记忆失败: {e}",
            )


class UpdateTaskStatusTool(Tool):
    """更新任务状态"""

    def __init__(self, memory: Memory):
        self._memory = memory

    @property
    def name(self) -> str:
        return "update_task_status"

    @property
    def description(self) -> str:
        return (
            "更新工作记忆中任务的状态。"
            "通常用于将 todo 标记为 completed。"
            "需要提供任务的 entry_id。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entry_id": {
                    "type": "string",
                    "description": "任务的 entry_id（从 store_working_memory 返回）",
                },
                "status": {
                    "type": "string",
                    "description": "新状态",
                    "enum": ["pending", "active", "completed", "cancelled"],
                },
            },
            "required": ["entry_id", "status"],
        }

    async def execute(self, entry_id: str, status: str) -> ToolResult:
        try:
            success = self._memory.update_working_status(entry_id, status)
            if success:
                return ToolResult(
                    success=True,
                    content=f"已更新任务 [{entry_id}] 状态为: {status}",
                )
            else:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"未找到任务: {entry_id}",
                )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"更新任务状态失败: {e}",
            )


class RecordDecisionTool(Tool):
    """记录重要决策"""

    def __init__(self, memory: Memory):
        self._memory = memory

    @property
    def name(self) -> str:
        return "record_decision"

    @property
    def description(self) -> str:
        return (
            "记录重要的技术决策或选择。"
            "包括决策内容和做出该决策的理由。"
            "用于追溯为什么采取了某种方案。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "description": "决策内容，例如：选择使用 Redis 作为缓存",
                },
                "reason": {
                    "type": "string",
                    "description": "决策理由，例如：项目已有 Redis 依赖，且性能需求高",
                },
            },
            "required": ["decision", "reason"],
        }

    async def execute(self, decision: str, reason: str) -> ToolResult:
        try:
            self._memory.add_decision(decision=decision, reason=reason)
            return ToolResult(
                success=True,
                content=f"已记录决策: {decision}\n理由: {reason}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"记录决策失败: {e}",
            )


class RecallMemoryTool(Tool):
    """查询记忆"""

    def __init__(self, memory: Memory):
        self._memory = memory

    @property
    def name(self) -> str:
        return "recall_memory"

    @property
    def description(self) -> str:
        return (
            "查询历史记忆。可以按类型筛选。"
            "返回最近的相关记忆条目。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "memory_type": {
                    "type": "string",
                    "description": "记忆类型筛选（可选）",
                    "enum": ["episodic", "semantic", "working", "all"],
                },
                "limit": {
                    "type": "integer",
                    "description": "返回条目数量上限，默认 10",
                    "minimum": 1,
                    "maximum": 50,
                },
            },
        }

    async def execute(
        self,
        memory_type: str = "all",
        limit: int = 10,
    ) -> ToolResult:
        try:
            if memory_type == "all":
                memories = self._memory.get_memories(limit=limit)
            else:
                mem_type = MemoryType(memory_type)
                memories = self._memory.get_memories(memory_type=mem_type, limit=limit)

            if not memories:
                return ToolResult(
                    success=True,
                    content="没有找到相关记忆。",
                )

            lines = [f"找到 {len(memories)} 条记忆:\n"]
            for i, mem in enumerate(memories, 1):
                mem_type_str = mem.get("type", "unknown")
                content = mem.get("content", "")
                metadata = mem.get("metadata", {})

                if mem_type_str == "episodic":
                    role = metadata.get("role", "")
                    round_num = metadata.get("round", "?")
                    lines.append(f"{i}. [对话 R{round_num}/{role}] {content[:100]}")
                elif mem_type_str == "semantic":
                    source = metadata.get("source", "")
                    lines.append(f"{i}. [知识/{source}] {content}")
                elif mem_type_str == "working":
                    category = metadata.get("category", "")
                    status = metadata.get("status", "")
                    lines.append(f"{i}. [{category}/{status}] {content}")
                else:
                    lines.append(f"{i}. [{mem_type_str}] {content}")

            return ToolResult(
                success=True,
                content="\n".join(lines),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"查询记忆失败: {e}",
            )


class GetMemorySummaryTool(Tool):
    """获取记忆摘要"""

    def __init__(self, memory: Memory):
        self._memory = memory

    @property
    def name(self) -> str:
        return "get_memory_summary"

    @property
    def description(self) -> str:
        return (
            "获取当前记忆系统的摘要。"
            "包括核心事实、待办任务、最近决策等。"
            "用于快速了解当前上下文。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self) -> ToolResult:
        try:
            lines = ["=== 记忆摘要 ===\n"]

            lines.append(f"任务: {self._memory.context.task or '未设置'}")
            lines.append(f"总记忆数: {self._memory.total_count}")
            lines.append(f"对话轮数: {self._memory.session_count // 2}\n")

            if self._memory.summary.core_facts:
                lines.append("核心事实:")
                for fact in self._memory.summary.core_facts:
                    lines.append(f"  - {fact}")
                lines.append("")

            pending = self._memory.get_pending_tasks()
            if pending:
                lines.append("待办任务:")
                for task in pending:
                    lines.append(f"  - [{task.get('id', '?')}] {task.get('content', '')}")
                lines.append("")

            if self._memory.summary.decisions:
                lines.append("最近决策:")
                for dec in self._memory.summary.decisions[-3:]:
                    lines.append(f"  - {dec.get('decision', '')}")
                lines.append("")

            return ToolResult(
                success=True,
                content="\n".join(lines),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"获取记忆摘要失败: {e}",
            )


def create_memory_tools(memory: Memory) -> list[Tool]:
    """创建所有记忆工具实例"""
    return [
        StoreSemanticMemoryTool(memory),
        StoreWorkingMemoryTool(memory),
        UpdateTaskStatusTool(memory),
        RecordDecisionTool(memory),
        RecallMemoryTool(memory),
        GetMemorySummaryTool(memory),
    ]
