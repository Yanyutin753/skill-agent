"""Agent 执行端点。"""
import json
import time
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from omni_agent.api.deps import (
    get_agent,
    get_settings,
    get_agent_session_manager,
    get_agent_factory,
    get_llm_client,
    get_builtin_research_team,
    AgentFactory,
)
from omni_agent.core import Agent, LLMClient, FileMemory
from omni_agent.core.team import Team
from omni_agent.core.config import Settings
from omni_agent.core.session import AgentRunRecord
from omni_agent.core.session_manager import UnifiedAgentSessionManager
from omni_agent.schemas.message import (
    AgentRequest, 
    AgentResponse, 
    AgentConfig, 
    Message,
    UserInputRequest,
    UserInputResponse,
)

router = APIRouter()


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    request: AgentRequest,
    agent_factory: AgentFactory = Depends(get_agent_factory),
    llm_client: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
    session_manager: Optional[UnifiedAgentSessionManager] = Depends(get_agent_session_manager),
    research_team: Team = Depends(get_builtin_research_team),
) -> AgentResponse:
    """执行 Agent 任务。

    Args:
        request: Agent 请求，包含消息和可选的动态配置
        agent_factory: Agent 工厂，用于创建动态配置的 Agent
        llm_client: LLM 客户端实例
        settings: 应用配置
        session_manager: 会话管理器，用于多轮对话
        research_team: 内置的 Web 研究团队（use_team=true 时注入）

    Returns:
        Agent 响应，包含结果和执行日志

    **团队模式:**
    - 设置 `use_team: true` 使用内置的 Web 研究团队
    - 团队包含 web_search_agent (exa) 和 web_spider_agent (firecrawl)
    - Leader 自动协调搜索和爬取任务

    **动态配置:**
    - 使用 `config` 字段按请求自定义 Agent 行为
    - 可覆盖 workspace_dir, max_steps, system_prompt, 工具选择等
    - 未提供时使用默认配置

    **会话支持:**
    - 提供 `session_id` 启用带历史上下文的多轮对话
    - 会话会持久化并可跨请求恢复

    **团队模式示例:**
    ```json
    {
        "message": "搜索 AI 新闻并爬取热门文章",
        "use_team": true,
        "session_id": "user-123"
    }
    ```

    **动态配置示例:**
    ```json
    {
        "message": "分析这段代码",
        "config": {
            "workspace_dir": "/tmp/custom-workspace",
            "max_steps": 20,
            "enable_base_tools": true,
            "enable_mcp_tools": false,
            "base_tools_filter": ["read", "write"]
        }
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
        # 检查是否启用团队模式
        if request.use_team:
            # 使用内置团队而不是单个 Agent
            response = await research_team.run(
                message=request.message,
                session_id=request.session_id,
                num_history_runs=request.num_history_runs or settings.SESSION_HISTORY_RUNS,
                max_steps=request.config.max_steps if request.config else settings.AGENT_MAX_STEPS,
            )

            # 将 TeamRunResponse 转换为 AgentResponse 格式
            return AgentResponse(
                success=response.success,
                message=response.message,
                steps=response.total_steps,
                logs=[],  # 当前实现中团队不暴露详细日志
                session_id=request.session_id,
                run_id=run_id,
            )

        # 原始单 Agent 模式
        # 处理向后兼容
        config = request.config
        if config is None:
            config = AgentConfig()

        # 支持已废弃的字段
        if request.workspace_dir and not config.workspace_dir:
            config.workspace_dir = request.workspace_dir
        if request.max_steps and not config.max_steps:
            config.max_steps = request.max_steps

        # 使用动态配置和会话隔离的工作空间创建 Agent
        agent = await agent_factory.create_agent(llm_client, config, session_id=request.session_id)

        # 如果提供了 session_id 则加载历史上下文
        if request.session_id and session_manager:
            session = await session_manager.get_session(
                session_id=request.session_id,
                agent_name="default"
            )
            # 获取历史消息并注入到 Agent
            history_messages = session.get_history_messages(
                num_runs=request.num_history_runs or settings.SESSION_HISTORY_RUNS
            )
            for msg in history_messages:
                agent.messages.append(Message(role=msg["role"], content=msg["content"]))

        # 添加用户消息并运行
        agent.add_user_message(request.message)
        result, logs = await agent.run()

        # 检查 Agent 是否正在等待用户输入
        if agent.is_waiting_for_input:
            # 存储 Agent 状态以便恢复（在实际应用中应使用适当的状态管理）
            # 目前我们返回输入请求，期望客户端调用 /run/resume
            return AgentResponse(
                success=True,
                message=result,
                steps=len([log for log in logs if log.get("type") == "step"]),
                logs=logs,
                session_id=request.session_id,
                run_id=run_id,
                requires_input=True,
                input_request=agent.pending_user_input,
            )

        # 判断是否成功
        success = bool(result and not result.startswith("LLM call failed"))
        steps = len([log for log in logs if log.get("type") == "step"])

        # 如果提供了 session_id 则保存到会话
        if request.session_id and session_manager:
            run_record = AgentRunRecord(
                run_id=run_id,
                task=request.message,
                response=result,
                success=success,
                steps=steps,
                timestamp=time.time(),
                metadata={"logs_count": len(logs)}
            )
            await session_manager.add_run(request.session_id, run_record)

        # 保存到 FileMemory (AGENTS.md)
        if request.session_id:
            memory = FileMemory(
                user_id=request.user_id or "default",
                session_id=request.session_id,
            )
            if not memory.exists():
                memory.init_memory(context=f"Task: {request.message}")
            tools_used = [log.get("tool") for log in logs if log.get("type") == "tool_call" and log.get("tool")]
            session = await session_manager.get_session(request.session_id, "default") if session_manager else None
            round_num = len(session.runs) if session else 1
            memory.append_round(round_num, request.message, result, tools_used or None)

        return AgentResponse(
            success=success,
            message=result,
            steps=steps,
            logs=logs,
            session_id=request.session_id,
            run_id=run_id,
        )

    except Exception as e:
        # 如果提供了 session_id 则保存错误到会话
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


@router.post("/run/stream")
async def run_agent_stream(
    request: AgentRequest,
    agent_factory: AgentFactory = Depends(get_agent_factory),
    llm_client: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
    session_manager: Optional[UnifiedAgentSessionManager] = Depends(get_agent_session_manager),
):
    """使用 Server-Sent Events 流式输出执行 Agent 任务。

    Args:
        request: Agent 请求，包含消息和可选的动态配置
        agent_factory: Agent 工厂，用于创建动态配置的 Agent
        llm_client: LLM 客户端实例
        settings: 应用配置
        session_manager: 会话管理器，用于多轮对话

    Returns:
        StreamingResponse: SSE 事件流

    **动态配置:**
    - 与 /run 端点相同，使用 `config` 字段自定义

    **会话支持:**
    - 与 /run 端点相同，提供 `session_id` 启用多轮对话
    """
    if not settings.LLM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API key not configured. Set LLM_API_KEY environment variable.",
        )

    run_id = str(uuid4())

    async def event_generator():
        """从 Agent 执行流生成 SSE 事件。"""
        content_buffer = ""
        steps = 0

        try:
            # 处理向后兼容
            config = request.config
            if config is None:
                config = AgentConfig()

            # 支持已废弃的字段
            if request.workspace_dir and not config.workspace_dir:
                config.workspace_dir = request.workspace_dir
            if request.max_steps and not config.max_steps:
                config.max_steps = request.max_steps

            # 使用动态配置和会话隔离的工作空间创建 Agent
            agent = await agent_factory.create_agent(llm_client, config, session_id=request.session_id)

            # 如果提供了 session_id 则加载历史上下文
            if request.session_id and session_manager:
                session = await session_manager.get_session(
                    session_id=request.session_id,
                    agent_name="default"
                )
                history_messages = session.get_history_messages(
                    num_runs=request.num_history_runs or settings.SESSION_HISTORY_RUNS
                )
                for msg in history_messages:
                    agent.messages.append(Message(role=msg["role"], content=msg["content"]))

                # 发送会话信息
                yield f"data: {json.dumps({'type': 'session', 'data': {'session_id': request.session_id, 'run_id': run_id}}, ensure_ascii=False)}\n\n"

            # 添加用户消息
            agent.add_user_message(request.message)

            # 流式执行 Agent
            async for event in agent.run_stream():
                event_type = event.get("type")
                event_data = event.get("data", {})

                # 跟踪内容和步骤用于会话
                if event_type == "content":
                    content_buffer += event_data.get("delta", "")
                elif event_type == "step":
                    steps += 1
                elif event_type == "done":
                    content_buffer = event_data.get("message", content_buffer)

                # 格式化为 SSE
                sse_data = json.dumps({
                    "type": event_type,
                    "data": event_data,
                }, ensure_ascii=False)

                yield f"data: {sse_data}\n\n"

            # 如果提供了 session_id 则保存到会话
            if request.session_id and session_manager:
                run_record = AgentRunRecord(
                    run_id=run_id,
                    task=request.message,
                    response=content_buffer,
                    success=True,
                    steps=steps,
                    timestamp=time.time(),
                    metadata={}
                )
                await session_manager.add_run(request.session_id, run_record)

            # 保存到 FileMemory (AGENTS.md)
            if request.session_id:
                memory = FileMemory(
                    user_id=request.user_id or "default",
                    session_id=request.session_id,
                )
                if not memory.exists():
                    memory.init_memory(context=f"Task: {request.message}")
                session = await session_manager.get_session(request.session_id, "default") if session_manager else None
                round_num = len(session.runs) if session else 1
                memory.append_round(round_num, request.message, content_buffer)

            # 发送最终完成事件
            yield "event: done\ndata: {}\n\n"

        except Exception as e:
            # 如果提供了 session_id 则保存错误到会话
            if request.session_id and session_manager:
                run_record = AgentRunRecord(
                    run_id=run_id,
                    task=request.message,
                    response=f"Error: {str(e)}",
                    success=False,
                    steps=steps,
                    timestamp=time.time(),
                    metadata={"error": str(e)}
                )
                await session_manager.add_run(request.session_id, run_record)

            # 发送错误事件
            error_data = json.dumps({
                "type": "error",
                "data": {"message": str(e)},
            })
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )
