"""Memory API 端点"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from omni_agent.core import MemoryManager, MemoryType

router = APIRouter()

manager = MemoryManager()


class MemoryEntryResponse(BaseModel):
    id: str
    content: str
    type: str
    importance: float
    timestamp: str
    metadata: dict


class MemoryListResponse(BaseModel):
    total: int
    memories: list[MemoryEntryResponse]


class MemorySummaryResponse(BaseModel):
    user_id: str
    session_id: str
    task: str
    total_memories: int
    session_count: int
    core_facts: list[str]
    pending_tasks: list[dict]
    decisions: list[dict]


class StoreMemoryRequest(BaseModel):
    content: str = Field(..., description="记忆内容")
    memory_type: str = Field("profile", description="记忆类型: profile, task")
    source: str | None = Field(None, description="信息来源 (profile 类型)")
    category: str | None = Field(None, description="分类 (task 类型): todo, progress, finding, error")
    importance: float = Field(0.5, ge=0, le=1, description="重要性 0-1")


class StoreMemoryResponse(BaseModel):
    success: bool
    entry_id: str
    message: str


class SessionListResponse(BaseModel):
    user_id: str
    sessions: list[str]


class StatsResponse(BaseModel):
    users: int
    sessions: int
    memories: int


@router.get("/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    """获取记忆系统统计信息"""
    stats = manager.get_stats()
    return StatsResponse(**stats)


@router.get("/users")
async def list_users() -> list[str]:
    """列出所有用户"""
    return manager.list_users()


@router.get("/users/{user_id}/sessions", response_model=SessionListResponse)
async def list_sessions(user_id: str) -> SessionListResponse:
    """列出用户的所有会话"""
    sessions = manager.list_sessions(user_id)
    return SessionListResponse(user_id=user_id, sessions=sessions)


@router.get(
    "/users/{user_id}/sessions/{session_id}",
    response_model=MemorySummaryResponse,
)
async def get_memory_summary(user_id: str, session_id: str) -> MemorySummaryResponse:
    """获取会话记忆摘要"""
    memory = manager.get_memory(user_id, session_id)
    if not memory.exists():
        raise HTTPException(status_code=404, detail="Memory not found")

    return MemorySummaryResponse(
        user_id=user_id,
        session_id=session_id,
        task=memory.context.task,
        total_memories=memory.total_count,
        session_count=memory.session_count,
        core_facts=memory.summary.core_facts,
        pending_tasks=memory.get_pending_tasks(),
        decisions=memory.summary.decisions,
    )


@router.get(
    "/users/{user_id}/sessions/{session_id}/memories",
    response_model=MemoryListResponse,
)
async def get_memories(
    user_id: str,
    session_id: str,
    memory_type: str | None = Query(None, description="过滤类型: session, profile, task, habit"),
    min_importance: float = Query(0.0, ge=0, le=1, description="最小重要性"),
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
) -> MemoryListResponse:
    """查询会话记忆"""
    memory = manager.get_memory(user_id, session_id)
    if not memory.exists():
        raise HTTPException(status_code=404, detail="Memory not found")

    mem_type = MemoryType(memory_type) if memory_type else None
    memories = memory.get_memories(
        memory_type=mem_type,
        min_importance=min_importance,
        limit=limit,
    )

    entries = [
        MemoryEntryResponse(
            id=m.get("id", ""),
            content=m.get("content", ""),
            type=m.get("type", ""),
            importance=m.get("importance", 0.5),
            timestamp=m.get("timestamp", 0),
            metadata=m.get("metadata", {}),
        )
        for m in memories
    ]

    return MemoryListResponse(total=len(entries), memories=entries)


@router.get(
    "/users/{user_id}/sessions/{session_id}/raw",
)
async def get_raw_memory(user_id: str, session_id: str) -> dict:
    """获取原始记忆数据 (完整 JSON)"""
    memory = manager.get_memory(user_id, session_id)
    if not memory.exists():
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory.to_dict()


@router.post(
    "/users/{user_id}/sessions/{session_id}/memories",
    response_model=StoreMemoryResponse,
)
async def store_memory(
    user_id: str,
    session_id: str,
    request: StoreMemoryRequest,
) -> StoreMemoryResponse:
    """存储记忆条目"""
    memory = manager.get_memory(user_id, session_id)
    if not memory.exists():
        memory.init_memory()

    try:
        if request.memory_type == "profile":
            entry_id = memory.add_profile(
                content=request.content,
                source=request.source or "api",
                importance=request.importance,
            )
        elif request.memory_type == "task":
            entry_id = memory.add_task(
                content=request.content,
                category=request.category or "general",
                importance=request.importance,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid memory_type: {request.memory_type}. Use 'profile' or 'task'.",
            )

        return StoreMemoryResponse(
            success=True,
            entry_id=entry_id,
            message=f"Memory stored: {request.content[:50]}...",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/users/{user_id}/sessions/{session_id}")
async def delete_session_memory(user_id: str, session_id: str) -> dict:
    """删除会话记忆"""
    success = manager.delete_session(user_id, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "message": f"Deleted memory for {user_id}/{session_id}"}


@router.delete("/users/{user_id}")
async def delete_user_memory(user_id: str) -> dict:
    """删除用户所有记忆"""
    success = manager.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "message": f"Deleted all memories for user {user_id}"}


@router.post("/cleanup")
async def cleanup_expired(max_age_days: int = Query(30, ge=1, le=365)) -> dict:
    """清理过期记忆"""
    removed = manager.cleanup_expired(max_age_days=max_age_days)
    return {"success": True, "removed_sessions": removed}
