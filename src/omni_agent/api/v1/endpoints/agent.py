"""Agent 执行端点。"""
import time
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from omni_agent.api.deps import (
    get_settings,
    get_agent_session_manager,
    get_default_team,
)
from omni_agent.core import FileMemory
from omni_agent.core.team import Team
from omni_agent.core.config import Settings
from omni_agent.core.session import AgentRunRecord
from omni_agent.core.session_manager import UnifiedAgentSessionManager
from omni_agent.schemas.message import AgentRequest, AgentResponse

router = APIRouter()


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    request: AgentRequest,
    team: Team = Depends(get_default_team),
    settings: Settings = Depends(get_settings),
    session_manager: Optional[UnifiedAgentSessionManager] = Depends(get_agent_session_manager),
) -> AgentResponse:
    """执行 Agent 任务。

    使用默认 Team 执行任务，Team 包含三个专业子 Agent：
    - General: 简单任务、问答、基础文件操作
    - Coder: 代码编写、修改、调试
    - Researcher: 信息搜索、网页内容获取

    Leader 负责分析任务并委派给合适的子 Agent 执行。

    Args:
        request: Agent 请求，包含 message, session_id, user_id

    Returns:
        Agent 响应，包含结果和执行信息

    **请求示例:**
    ```json
    {
        "message": "帮我写一个快速排序算法",
        "session_id": "user-123"
    }
    ```
    """
    if not settings.LLM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API key not configured. Set LLM_API_KEY environment variable.",
        )

    run_id = str(uuid4())

    try:
        response = await team.run(
            message=request.message,
            session_id=request.session_id,
            num_history_runs=settings.SESSION_HISTORY_RUNS,
            max_steps=settings.AGENT_MAX_STEPS,
        )

        success = response.success
        result = response.message
        steps = response.total_steps

        if request.session_id and session_manager:
            run_record = AgentRunRecord(
                run_id=run_id,
                task=request.message,
                response=result,
                success=success,
                steps=steps,
                timestamp=time.time(),
                metadata={}
            )
            await session_manager.add_run(request.session_id, run_record)

        if request.session_id:
            memory = FileMemory(
                user_id=request.user_id or "default",
                session_id=request.session_id,
            )
            if not memory.exists():
                memory.init_memory(context=f"Task: {request.message}")
            session = await session_manager.get_session(request.session_id, "default") if session_manager else None
            round_num = len(session.runs) if session else 1
            memory.append_round(round_num, request.message, result)

        return AgentResponse(
            success=success,
            message=result,
            steps=steps,
            logs=[],
            session_id=request.session_id,
            run_id=run_id,
        )

    except Exception as e:
        if request.session_id and session_manager:
            run_record = AgentRunRecord(
                run_id=run_id,
                task=request.message,
                response=f"Error: {str(e)}",
                success=False,
                steps=0,
                timestamp=time.time(),
                metadata={"error": str(e)}
            )
            await session_manager.add_run(request.session_id, run_record)

        raise HTTPException(
            status_code=500, detail=f"Agent execution failed: {str(e)}"
        ) from e
