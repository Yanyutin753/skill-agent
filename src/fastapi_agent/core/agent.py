"""Core Agent implementation with refactored architecture."""

import json
from pathlib import Path
from typing import Any, AsyncIterator, Optional, TYPE_CHECKING

from fastapi_agent.core.agent_events import EventEmitter, EventType, AgentEvent
from fastapi_agent.core.agent_loop import AgentLoop, LoopConfig
from fastapi_agent.core.agent_state import AgentState, AgentStatus
from fastapi_agent.core.langfuse_tracing import get_tracer, LangfuseTracer
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.token_manager import TokenManager
from fastapi_agent.core.tool_executor import ToolExecutor
from fastapi_agent.core.prompt_builder import SystemPromptConfig, SystemPromptBuilder
from fastapi_agent.schemas.message import Message, UserInputRequest, UserInputField
from fastapi_agent.skills.skill_loader import SkillLoader
from fastapi_agent.tools.base import Tool
from fastapi_agent.tools.user_input_tool import GetUserInputTool


class Agent:
    """Agent with tool execution loop using event-driven architecture."""

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: Optional[str] = None,
        prompt_config: Optional[SystemPromptConfig] = None,
        tools: list[Tool] | None = None,
        max_steps: int = 50,
        workspace_dir: str = "./workspace",
        token_limit: int = 120000,
        enable_summarization: bool = True,
        enable_logging: bool = True,
        log_dir: str | None = None,
        name: str | None = None,
        skill_loader: Optional[SkillLoader] = None,
        tool_output_limit: int = 10000,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        parallel_tools: bool = False,
    ) -> None:
        self.llm = llm_client
        self.name = name or "agent"
        self.tools = {tool.name: tool for tool in (tools or [])}
        self.max_steps = max_steps
        self.workspace_dir = Path(workspace_dir)
        self.skill_loader = skill_loader
        self.tool_output_limit = tool_output_limit
        self.user_id = user_id
        self.session_id = session_id
        self.enable_logging = enable_logging

        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        self._state = AgentState(max_steps=max_steps)
        self._events = EventEmitter()

        self.token_manager = TokenManager(
            llm_client=llm_client,
            token_limit=token_limit,
            enable_summarization=enable_summarization,
        )

        self._tool_executor = ToolExecutor(
            tools=self.tools,
            output_limit=tool_output_limit,
            parallel_execution=parallel_tools,
        )

        self._loop = AgentLoop(
            llm_client=llm_client,
            tool_executor=self._tool_executor,
            token_manager=self.token_manager,
            event_emitter=self._events,
            config=LoopConfig(max_steps=max_steps, parallel_tools=parallel_tools),
        )
        self._loop.set_tools(self.tools)

        self.tracer: Optional[LangfuseTracer] = None
        self.execution_logs: list[dict[str, Any]] = []

        if prompt_config:
            self.system_prompt = self._build_structured_prompt(prompt_config)
        elif system_prompt:
            if "Current Workspace" not in system_prompt and "workspace_info" not in system_prompt:
                workspace_info = (
                    f"\n\n## Current Workspace\n"
                    f"You are currently working in: `{self.workspace_dir.absolute()}`\n"
                    f"All relative paths will be resolved relative to this directory."
                )
                system_prompt = system_prompt + workspace_info
            self.system_prompt = system_prompt
        else:
            self.system_prompt = self._build_default_prompt()

        self._state.messages = [Message(role="system", content=self.system_prompt)]

    @property
    def messages(self) -> list[Message]:
        return self._state.messages

    @messages.setter
    def messages(self, value: list[Message]) -> None:
        self._state.messages = value

    def _collect_tool_instructions(self) -> list[str]:
        instructions = []
        for tool in self.tools.values():
            if tool.add_instructions_to_prompt and tool.instructions:
                instructions.append(tool.instructions)
        return instructions

    def _build_structured_prompt(self, config: SystemPromptConfig) -> str:
        tool_instructions = self._collect_tool_instructions()
        builder = SystemPromptBuilder()
        return builder.build(
            config=config,
            workspace_dir=self.workspace_dir,
            skill_loader=self.skill_loader,
            tool_instructions=tool_instructions,
        )

    def _build_default_prompt(self) -> str:
        config = SystemPromptConfig(
            description="You are a helpful AI assistant.",
            instructions=[
                "Always think step by step",
                "Use available tools when appropriate",
                "Provide clear and accurate responses",
            ],
        )
        return self._build_structured_prompt(config)

    def add_user_message(self, content: str) -> None:
        self._state.messages.append(Message(role="user", content=content))

    def _setup_execution_logging(self) -> None:
        self.execution_logs = []

        async def collect_step_start(event: AgentEvent) -> None:
            self.execution_logs.append({
                "type": "step",
                "step": event.step,
                "max_steps": event.data.get("max_steps", self.max_steps),
                "tokens": event.data.get("tokens", 0),
                "token_limit": event.data.get("token_limit", self.token_manager.token_limit),
            })
            if self.tracer:
                self.tracer.log_step(
                    step=event.step,
                    max_steps=event.data.get("max_steps", self.max_steps),
                    token_count=event.data.get("tokens", 0),
                    token_limit=event.data.get("token_limit", self.token_manager.token_limit),
                )

        async def collect_llm_response(event: AgentEvent) -> None:
            self.execution_logs.append({
                "type": "llm_response",
                "thinking": event.data.get("thinking"),
                "content": event.data.get("content"),
                "has_tool_calls": event.data.get("has_tool_calls", False),
                "tool_count": event.data.get("tool_count", 0),
                "input_tokens": event.data.get("input_tokens", 0),
                "output_tokens": event.data.get("output_tokens", 0),
            })
            if self.tracer and event.data.get("input_tokens"):
                self.tracer.log_llm_response(
                    input_tokens=event.data.get("input_tokens", 0),
                    output_tokens=event.data.get("output_tokens", 0),
                )

        async def collect_tool_start(event: AgentEvent) -> None:
            self.execution_logs.append({
                "type": "tool_call",
                "tool": event.data.get("tool"),
                "arguments": event.data.get("arguments"),
            })

        async def collect_tool_end(event: AgentEvent) -> None:
            if self.tracer:
                pass
            else:
                self.execution_logs.append({
                    "type": "tool_result",
                    "tool": event.data.get("tool"),
                    "success": event.data.get("success"),
                    "content": event.data.get("content"),
                    "error": event.data.get("error"),
                    "execution_time": event.data.get("execution_time"),
                })

        async def collect_user_input(event: AgentEvent) -> None:
            self.execution_logs.append({
                "type": "user_input_required",
                "tool_call_id": event.data.get("tool_call_id"),
                "fields": event.data.get("fields"),
                "context": event.data.get("context"),
            })

        async def collect_completion(event: AgentEvent) -> None:
            self.execution_logs.append({
                "type": "completion",
                "message": "Task completed successfully",
                "total_input_tokens": event.data.get("total_input_tokens", 0),
                "total_output_tokens": event.data.get("total_output_tokens", 0),
                "total_tokens": (
                    event.data.get("total_input_tokens", 0) +
                    event.data.get("total_output_tokens", 0)
                ),
            })
            if self.tracer:
                self.tracer.end_trace(
                    success=True,
                    final_response=event.data.get("message", ""),
                    total_steps=event.data.get("total_steps", self._state.current_step),
                    reason="task_completed",
                )

        async def collect_error(event: AgentEvent) -> None:
            reason = event.data.get("reason", "error")
            if reason == "max_steps_reached":
                self.execution_logs.append({
                    "type": "max_steps_reached",
                    "message": event.data.get("message"),
                    "total_input_tokens": self._state.total_input_tokens,
                    "total_output_tokens": self._state.total_output_tokens,
                    "total_tokens": self._state.total_tokens,
                })
            else:
                self.execution_logs.append({
                    "type": "error",
                    "message": event.data.get("message"),
                })
            if self.tracer:
                self.tracer.end_trace(
                    success=False,
                    final_response=event.data.get("message", ""),
                    total_steps=self._state.current_step,
                    reason=reason,
                )

        self._events.clear()
        self._events.on(EventType.STEP_START, collect_step_start)
        self._events.on(EventType.LLM_RESPONSE, collect_llm_response)
        self._events.on(EventType.TOOL_START, collect_tool_start)
        self._events.on(EventType.TOOL_END, collect_tool_end)
        self._events.on(EventType.USER_INPUT_REQUIRED, collect_user_input)
        self._events.on(EventType.COMPLETION, collect_completion)
        self._events.on(EventType.ERROR, collect_error)

    def _setup_tracer(self) -> None:
        if not self.enable_logging:
            self.tracer = None
            return

        self.tracer = get_tracer(
            name=self.name,
            user_id=self.user_id,
            session_id=self.session_id,
            metadata={"max_steps": self.max_steps},
        )
        task = ""
        if self._state.messages and len(self._state.messages) > 1:
            for msg in reversed(self._state.messages):
                if msg.role == "user":
                    task = msg.content[:200] if msg.content else ""
                    break
        self.tracer.start_trace(task)

    async def run(self) -> tuple[str, list[dict[str, Any]]]:
        self._setup_tracer()
        self._setup_execution_logging()

        result = await self._loop.run(self._state, self._get_llm_metadata())

        return result, self.execution_logs

    async def run_stream(self) -> AsyncIterator[dict[str, Any]]:
        self._setup_tracer()
        self._setup_execution_logging()

        async for event in self._loop.run_stream(self._state, self._get_llm_metadata()):
            yield event

    def _get_llm_metadata(self) -> Optional[dict[str, Any]]:
        if self.tracer:
            return self.tracer.get_litellm_metadata()
        return None

    def get_history(self) -> list[Message]:
        return self._state.messages.copy()

    @property
    def pending_user_input(self) -> Optional[UserInputRequest]:
        return self._state.pending_user_input

    @property
    def is_waiting_for_input(self) -> bool:
        return self._state.is_waiting_input

    def provide_user_input(self, field_values: dict[str, Any]) -> None:
        if not self._state.pending_user_input:
            raise ValueError("No pending user input request")

        for field in self._state.pending_user_input.fields:
            if field.field_name in field_values:
                field.value = field_values[field.field_name]

        user_input_result = [
            {"name": field.field_name, "value": field.value}
            for field in self._state.pending_user_input.fields
        ]

        tool_msg = Message(
            role="tool",
            content=f"User inputs received: {json.dumps(user_input_result, ensure_ascii=False)}",
            tool_call_id=self._state.pending_user_input.tool_call_id,
            name=GetUserInputTool.TOOL_NAME,
        )
        self._state.messages.append(tool_msg)

        self.execution_logs.append({
            "type": "user_input_received",
            "tool_call_id": self._state.pending_user_input.tool_call_id,
            "field_values": field_values,
        })

        self._state.resume_from_input()

    async def resume(self) -> tuple[str, list[dict[str, Any]]]:
        if self._state.pending_user_input:
            raise ValueError("Cannot resume: still waiting for user input. Call provide_user_input first.")
        return await self.run()

    async def resume_stream(self) -> AsyncIterator[dict[str, Any]]:
        if self._state.pending_user_input:
            raise ValueError("Cannot resume: still waiting for user input. Call provide_user_input first.")
        async for event in self.run_stream():
            yield event

    # Backward compatibility aliases
    @property
    def _pending_user_input(self) -> Optional[UserInputRequest]:
        return self._state.pending_user_input

    @_pending_user_input.setter
    def _pending_user_input(self, value: Optional[UserInputRequest]) -> None:
        self._state.pending_user_input = value

    @property
    def _current_step(self) -> int:
        return self._state.current_step

    @_current_step.setter
    def _current_step(self, value: int) -> None:
        self._state.current_step = value

    @property
    def _paused_tool_call_id(self) -> Optional[str]:
        return self._state.paused_tool_call_id

    @_paused_tool_call_id.setter
    def _paused_tool_call_id(self, value: Optional[str]) -> None:
        self._state.paused_tool_call_id = value

    def _truncate_tool_output(self, content: str) -> str:
        if len(content) <= self.tool_output_limit:
            return content
        truncated = content[:self.tool_output_limit]
        return f"{truncated}\n\n[... output truncated, {len(content) - self.tool_output_limit} more characters ...]"
