"""ACP (Agent Client Protocol) endpoints.

Implements Zed's Agent Client Protocol for standardized communication
between code editors and coding agents.

Protocol spec: https://agentclientprotocol.com/
"""

import json
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from omni_agent.acp.adapter import ACPAdapter
from omni_agent.acp.schemas import (
    JsonRpcRequest,
    JsonRpcResponse,
    InitializeRequest,
    SessionNewRequest,
    SessionPromptRequest,
    ToolCallStatus,
)
from omni_agent.api.deps import (
    get_agent_factory,
    get_llm_client,
    get_settings,
    AgentFactory,
)
from omni_agent.core import LLMClient
from omni_agent.core.config import Settings
from omni_agent.schemas.message import Message, AgentConfig

router = APIRouter(prefix="/acp", tags=["ACP"])

_sessions: dict[str, dict] = {}


@router.post("/agent/initialize")
async def initialize(
    request: JsonRpcRequest,
    settings: Settings = Depends(get_settings),
) -> JsonRpcResponse:
    """Initialize ACP connection and negotiate capabilities.

    ACP endpoint: POST /agent/initialize
    """
    init_response = ACPAdapter.create_initialize_response(
        name="omni-agent",
        version=settings.VERSION,
        title=settings.PROJECT_NAME,
    )
    return ACPAdapter.wrap_jsonrpc_response(
        request.id,
        init_response.model_dump(by_alias=True),
    )


@router.post("/session/new")
async def create_session(
    request: JsonRpcRequest,
    settings: Settings = Depends(get_settings),
) -> JsonRpcResponse:
    """Create a new agent session.

    ACP endpoint: POST /session/new
    """
    params = request.params or {}
    session_id = f"sess_{uuid4().hex[:12]}"

    _sessions[session_id] = {
        "cwd": params.get("cwd", settings.AGENT_WORKSPACE_DIR),
        "mcp_servers": params.get("mcpServers", []),
        "messages": [],
    }

    response = ACPAdapter.create_session_response(session_id)
    return ACPAdapter.wrap_jsonrpc_response(
        request.id,
        response.model_dump(by_alias=True),
    )


@router.post("/session/prompt")
async def session_prompt(
    request: JsonRpcRequest,
    agent_factory: AgentFactory = Depends(get_agent_factory),
    llm_client: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
) -> JsonRpcResponse:
    """Process a user prompt in an existing session.

    ACP endpoint: POST /session/prompt
    This is a synchronous endpoint. For streaming, use /session/prompt/stream.
    """
    if not settings.LLM_API_KEY:
        return ACPAdapter.wrap_jsonrpc_error(
            request.id,
            code=-32000,
            message="API key not configured",
        )

    params = request.params or {}
    session_id = params.get("sessionId")
    prompt = params.get("prompt", [])

    if not session_id or session_id not in _sessions:
        return ACPAdapter.wrap_jsonrpc_error(
            request.id,
            code=-32001,
            message="Invalid or missing session ID",
        )

    user_message = ACPAdapter.prompt_to_internal_message(prompt)
    if not user_message:
        return ACPAdapter.wrap_jsonrpc_error(
            request.id,
            code=-32002,
            message="Empty prompt",
        )

    try:
        session = _sessions[session_id]
        config = AgentConfig(workspace_dir=session["cwd"])
        agent = await agent_factory.create_agent(llm_client, config, session_id=session_id)

        for msg in session["messages"]:
            agent.messages.append(Message(role=msg["role"], content=msg["content"]))

        agent.add_user_message(user_message)
        result, _ = await agent.run()

        session["messages"].append({"role": "user", "content": user_message})
        session["messages"].append({"role": "assistant", "content": result})

        response = ACPAdapter.create_prompt_response(session_id, stop_reason="endoftext")
        return ACPAdapter.wrap_jsonrpc_response(
            request.id,
            response.model_dump(by_alias=True),
        )

    except Exception as e:
        return ACPAdapter.wrap_jsonrpc_error(
            request.id,
            code=-32603,
            message=str(e),
        )


@router.post("/session/prompt/stream")
async def session_prompt_stream(
    request: JsonRpcRequest,
    agent_factory: AgentFactory = Depends(get_agent_factory),
    llm_client: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
):
    """Process a user prompt with streaming session updates.

    Returns Server-Sent Events with ACP session/update notifications.
    """
    if not settings.LLM_API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    params = request.params or {}
    session_id = params.get("sessionId")
    prompt = params.get("prompt", [])

    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    user_message = ACPAdapter.prompt_to_internal_message(prompt)
    if not user_message:
        raise HTTPException(status_code=400, detail="Empty prompt")

    async def event_generator():
        try:
            session = _sessions[session_id]
            config = AgentConfig(workspace_dir=session["cwd"])
            agent = await agent_factory.create_agent(llm_client, config, session_id=session_id)

            for msg in session["messages"]:
                agent.messages.append(Message(role=msg["role"], content=msg["content"]))

            agent.add_user_message(user_message)

            content_buffer = ""
            async for event in agent.run_stream():
                event_type = event.get("type")
                event_data = event.get("data", {})

                if event_type == "thinking":
                    update = ACPAdapter.create_thought_update(
                        session_id,
                        event_data.get("delta", ""),
                    )
                    yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'session/update', 'params': update.model_dump(by_alias=True)})}\n\n"

                elif event_type == "content":
                    delta = event_data.get("delta", "")
                    content_buffer += delta
                    update = ACPAdapter.create_message_update(session_id, delta)
                    yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'session/update', 'params': update.model_dump(by_alias=True)})}\n\n"

                elif event_type == "tool_call":
                    tool_name = event_data.get("tool", "unknown")
                    arguments = event_data.get("arguments", {})
                    tool_call_id = f"tc_{uuid4().hex[:8]}"
                    update = ACPAdapter.create_tool_call_update(
                        session_id,
                        tool_call_id,
                        tool_name,
                        arguments,
                        status=ToolCallStatus.IN_PROGRESS,
                    )
                    yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'session/update', 'params': update.model_dump(by_alias=True)})}\n\n"

                elif event_type == "tool_result":
                    tool_call_id = f"tc_{uuid4().hex[:8]}"
                    update = ACPAdapter.create_tool_result_update(
                        session_id,
                        tool_call_id,
                        success=event_data.get("success", True),
                        content=event_data.get("content"),
                        error=event_data.get("error"),
                    )
                    yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'session/update', 'params': update.model_dump(by_alias=True)})}\n\n"

                elif event_type == "done":
                    content_buffer = event_data.get("message", content_buffer)

            session["messages"].append({"role": "user", "content": user_message})
            session["messages"].append({"role": "assistant", "content": content_buffer})

            response = ACPAdapter.create_prompt_response(session_id, stop_reason="endoftext")
            yield f"data: {json.dumps({'jsonrpc': '2.0', 'id': request.id, 'result': response.model_dump(by_alias=True)})}\n\n"

        except Exception as e:
            error_response = ACPAdapter.wrap_jsonrpc_error(request.id, -32603, str(e))
            yield f"data: {json.dumps(error_response.model_dump())}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/session/cancel")
async def cancel_session(
    request: JsonRpcRequest,
) -> JsonRpcResponse:
    """Cancel an ongoing session operation.

    ACP endpoint: POST /session/cancel
    """
    params = request.params or {}
    session_id = params.get("sessionId")

    if not session_id or session_id not in _sessions:
        return ACPAdapter.wrap_jsonrpc_error(
            request.id,
            code=-32001,
            message="Invalid session ID",
        )

    return ACPAdapter.wrap_jsonrpc_response(
        request.id,
        {"cancelled": True},
    )


@router.delete("/session/{session_id}")
async def delete_session(session_id: str) -> dict:
    """Delete a session.

    Not part of ACP spec but useful for cleanup.
    """
    if session_id in _sessions:
        del _sessions[session_id]
        return {"deleted": True}
    raise HTTPException(status_code=404, detail="Session not found")
