"""Agent execution endpoints."""

import json
import time
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from fastapi_agent.api.deps import get_agent, get_settings, get_agent_session_manager
from fastapi_agent.core import Agent
from fastapi_agent.core.config import Settings
from fastapi_agent.core.session import AgentRunRecord
from fastapi_agent.core.session_manager import UnifiedAgentSessionManager
from fastapi_agent.schemas.message import AgentRequest, AgentResponse, Message

router = APIRouter()


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    request: AgentRequest,
    agent: Agent = Depends(get_agent),
    settings: Settings = Depends(get_settings),
    session_manager: Optional[UnifiedAgentSessionManager] = Depends(get_agent_session_manager),
) -> AgentResponse:
    """Run agent with a task.

    Args:
        request: Agent request with message and optional parameters
        agent: Agent instance from dependency injection
        settings: Application settings
        session_manager: Session manager for multi-turn conversation

    Returns:
        Agent response with result and execution logs

    **Session support:**
    - Provide `session_id` to enable multi-turn conversation with history context
    - Sessions are persisted and can be resumed across requests

    **Example with session:**
    ```json
    {
        "message": "What is Python?",
        "session_id": "user-123"
    }
    ```

    Then in the next request:
    ```json
    {
        "message": "Tell me more about its syntax",
        "session_id": "user-123"
    }
    ```
    The agent will have context from the previous conversation.
    """
    if not settings.LLM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API key not configured. Set LLM_API_KEY environment variable.",
        )

    run_id = str(uuid4())

    try:
        # Load history context if session_id provided
        if request.session_id and session_manager:
            session = await session_manager.get_session(
                session_id=request.session_id,
                agent_name="default"
            )
            # Get history messages and inject into agent
            history_messages = session.get_history_messages(
                num_runs=request.num_history_runs or settings.SESSION_HISTORY_RUNS
            )
            for msg in history_messages:
                agent.messages.append(Message(role=msg["role"], content=msg["content"]))

        # Add user message and run
        agent.add_user_message(request.message)
        result, logs = await agent.run()

        # Determine success
        success = bool(result and not result.startswith("LLM call failed"))
        steps = len([log for log in logs if log.get("type") == "step"])

        # Save to session if session_id provided
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

        return AgentResponse(
            success=success,
            message=result,
            steps=steps,
            logs=logs,
            session_id=request.session_id,
            run_id=run_id,
        )

    except Exception as e:
        # Save error to session if session_id provided
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
    agent: Agent = Depends(get_agent),
    settings: Settings = Depends(get_settings),
    session_manager: Optional[UnifiedAgentSessionManager] = Depends(get_agent_session_manager),
):
    """Run agent with streaming output using Server-Sent Events.

    Args:
        request: Agent request with message and optional parameters
        agent: Agent instance from dependency injection
        settings: Application settings
        session_manager: Session manager for multi-turn conversation

    Returns:
        StreamingResponse with SSE events

    **Session support:**
    - Same as /run endpoint, provide `session_id` for multi-turn conversation
    """
    if not settings.LLM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API key not configured. Set LLM_API_KEY environment variable.",
        )

    run_id = str(uuid4())

    async def event_generator():
        """Generate SSE events from agent stream."""
        content_buffer = ""
        steps = 0

        try:
            # Load history context if session_id provided
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

                # Send session info
                yield f"data: {json.dumps({'type': 'session', 'data': {'session_id': request.session_id, 'run_id': run_id}}, ensure_ascii=False)}\n\n"

            # Add user message
            agent.add_user_message(request.message)

            # Stream agent execution
            async for event in agent.run_stream():
                event_type = event.get("type")
                event_data = event.get("data", {})

                # Track content and steps for session
                if event_type == "content":
                    content_buffer += event_data.get("delta", "")
                elif event_type == "step":
                    steps += 1
                elif event_type == "done":
                    content_buffer = event_data.get("message", content_buffer)

                # Format as SSE
                sse_data = json.dumps({
                    "type": event_type,
                    "data": event_data,
                }, ensure_ascii=False)

                yield f"data: {sse_data}\n\n"

            # Save to session if session_id provided
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

            # Send final done event
            yield "event: done\ndata: {}\n\n"

        except Exception as e:
            # Save error to session if session_id provided
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

            # Send error event
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
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
