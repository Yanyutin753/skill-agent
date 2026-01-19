"""核心 Agent 实现，采用统一架构。"""
import json
import time
from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Awaitable, Optional
from uuid import uuid4

from omni_agent.core.checkpoint import Checkpoint, CheckpointConfig
from omni_agent.core.langfuse_tracing import get_tracer, LangfuseTracer
from omni_agent.core.llm_client import LLMClient
from omni_agent.core.token_manager import TokenManager
from omni_agent.core.tool_executor import ToolExecutor
from omni_agent.core.prompt_builder import SystemPromptConfig, SystemPromptBuilder
from omni_agent.schemas.message import Message, UserInputRequest, UserInputField, ToolCall
from omni_agent.skills.skill_loader import SkillLoader
from omni_agent.tools.base import Tool
from omni_agent.tools.user_input_tool import GetUserInputTool, is_user_input_tool_call, parse_user_input_fields


class EventType(Enum):
    STEP_START = "step_start"
    STEP_END = "step_end"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    USER_INPUT_REQUIRED = "user_input_required"
    COMPLETION = "completion"
    ERROR = "error"
    TOKEN_SUMMARY = "token_summary"


@dataclass
class AgentEvent:
    type: EventType
    data: dict[str, Any]
    step: int = 0
    timestamp: float = field(default_factory=time.time)


EventHandler = Callable[[AgentEvent], Awaitable[None]]


class EventEmitter:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []

    def on(self, event_type: EventType, handler: EventHandler) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def off(self, event_type: EventType, handler: EventHandler) -> None:
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def on_all(self, handler: EventHandler) -> None:
        self._global_handlers.append(handler)

    def off_all(self, handler: EventHandler) -> None:
        if handler in self._global_handlers:
            self._global_handlers.remove(handler)

    async def emit(self, event: AgentEvent) -> None:
        for handler in self._global_handlers:
            await handler(event)
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            await handler(event)

    def clear(self) -> None:
        self._handlers.clear()
        self._global_handlers.clear()


class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentState:
    status: AgentStatus = AgentStatus.IDLE
    current_step: int = 0
    max_steps: int = 50
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    messages: list[Message] = field(default_factory=list)
    pending_user_input: Optional[UserInputRequest] = None
    paused_tool_call_id: Optional[str] = None
    error_message: Optional[str] = None
    last_checkpoint_id: Optional[str] = None
    thread_id: Optional[str] = None

    def reset_for_run(self, preserve_messages: bool = False) -> None:
        self.status = AgentStatus.RUNNING
        self.current_step = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.pending_user_input = None
        self.paused_tool_call_id = None
        self.error_message = None
        if not preserve_messages:
            self.last_checkpoint_id = None

    def increment_step(self) -> int:
        self.current_step += 1
        return self.current_step

    def add_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def mark_waiting_input(self, request: UserInputRequest, tool_call_id: str) -> None:
        self.status = AgentStatus.WAITING_INPUT
        self.pending_user_input = request
        self.paused_tool_call_id = tool_call_id

    def mark_completed(self) -> None:
        self.status = AgentStatus.COMPLETED
        self.pending_user_input = None
        self.paused_tool_call_id = None

    def mark_error(self, message: str) -> None:
        self.status = AgentStatus.ERROR
        self.error_message = message

    def resume_from_input(self) -> None:
        if self.status == AgentStatus.WAITING_INPUT:
            self.status = AgentStatus.RUNNING
            self.pending_user_input = None
            self.paused_tool_call_id = None

    def resume_from_checkpoint(self) -> None:
        if self.status in (AgentStatus.IDLE, AgentStatus.COMPLETED, AgentStatus.ERROR):
            self.status = AgentStatus.RUNNING
            self.error_message = None

    @property
    def is_running(self) -> bool:
        return self.status == AgentStatus.RUNNING

    @property
    def is_waiting_input(self) -> bool:
        return self.status == AgentStatus.WAITING_INPUT

    @property
    def is_completed(self) -> bool:
        return self.status == AgentStatus.COMPLETED

    @property
    def is_error(self) -> bool:
        return self.status == AgentStatus.ERROR

    @property
    def can_continue(self) -> bool:
        return self.status == AgentStatus.RUNNING and self.current_step < self.max_steps

    def to_checkpoint_data(self) -> dict:
        return {
            "step": self.current_step,
            "status": self.status.value,
            "messages": self.messages,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "pending_user_input": self.pending_user_input,
            "paused_tool_call_id": self.paused_tool_call_id,
            "error_message": self.error_message,
        }

    @classmethod
    def from_checkpoint(cls, checkpoint: "Checkpoint", max_steps: int = 50) -> "AgentState":
        return cls(
            status=AgentStatus(checkpoint.status),
            current_step=checkpoint.step,
            max_steps=max_steps,
            total_input_tokens=checkpoint.token_usage.get("input", 0),
            total_output_tokens=checkpoint.token_usage.get("output", 0),
            messages=checkpoint.get_messages(),
            last_checkpoint_id=checkpoint.id,
            thread_id=checkpoint.thread_id,
        )


@dataclass
class HookContext:
    state: AgentState
    step: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentHook(ABC):
    priority: int = 100

    async def before_run(self, ctx: HookContext) -> None:
        pass

    async def on_step(self, ctx: HookContext, step_data: dict[str, Any]) -> None:
        pass

    async def after_run(self, ctx: HookContext, result: str, success: bool) -> None:
        pass


class HookManager:
    def __init__(self) -> None:
        self._hooks: list[AgentHook] = []

    def add(self, hook: AgentHook) -> None:
        self._hooks.append(hook)
        self._hooks.sort(key=lambda h: h.priority)

    def remove(self, hook: AgentHook) -> None:
        if hook in self._hooks:
            self._hooks.remove(hook)

    def clear(self) -> None:
        self._hooks.clear()

    async def trigger_before_run(self, ctx: HookContext) -> None:
        for hook in self._hooks:
            await hook.before_run(ctx)

    async def trigger_on_step(self, ctx: HookContext, step_data: dict[str, Any]) -> None:
        for hook in self._hooks:
            await hook.on_step(ctx, step_data)

    async def trigger_after_run(self, ctx: HookContext, result: str, success: bool) -> None:
        for hook in self._hooks:
            await hook.after_run(ctx, result, success)


@dataclass
class LoopConfig:
    max_steps: int = 50
    parallel_tools: bool = False
    checkpoint: Optional[CheckpointConfig] = None


@dataclass
class StepResult:
    completed: bool = False
    waiting_input: bool = False
    content: str = ""
    error: Optional[str] = None


class AgentLoop:
    def __init__(
        self,
        llm_client: LLMClient,
        tool_executor: ToolExecutor,
        token_manager: TokenManager,
        event_emitter: EventEmitter,
        config: Optional[LoopConfig] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        self._llm = llm_client
        self._tool_executor = tool_executor
        self._token_manager = token_manager
        self._events = event_emitter
        self._config = config or LoopConfig()
        self._tool_schemas: Optional[list[dict[str, Any]]] = None
        self._agent_id = agent_id or str(uuid4())
        self._hooks = HookManager()

    @property
    def checkpoint_enabled(self) -> bool:
        return (
            self._config.checkpoint is not None
            and self._config.checkpoint.enabled
            and self._config.checkpoint.storage is not None
        )

    async def _save_checkpoint(
        self,
        state: AgentState,
        trigger: str,
        pending_tool_calls: Optional[list[ToolCall]] = None,
    ) -> Optional[str]:
        if not self.checkpoint_enabled:
            return None

        config = self._config.checkpoint
        assert config is not None
        storage = config.get_storage()

        checkpoint = Checkpoint.create(
            agent_id=self._agent_id,
            thread_id=state.thread_id or str(uuid4()),
            step=state.current_step,
            status=state.status.value,
            messages=state.messages,
            pending_tool_calls=pending_tool_calls,
            input_tokens=state.total_input_tokens,
            output_tokens=state.total_output_tokens,
            metadata={"trigger": trigger},
            parent_id=state.last_checkpoint_id,
        )

        await storage.save(checkpoint)
        state.last_checkpoint_id = checkpoint.id

        if config.max_checkpoints_per_thread > 0:
            existing = await storage.list_checkpoints(
                checkpoint.thread_id,
                limit=config.max_checkpoints_per_thread + 10,
            )
            if len(existing) > config.max_checkpoints_per_thread:
                for old_cp in existing[config.max_checkpoints_per_thread:]:
                    await storage.delete(old_cp.id)

        return checkpoint.id

    def set_tools(self, tools: dict[str, Tool]) -> None:
        self._tool_executor.set_tools(tools)
        self._tool_schemas = [tool.to_schema() for tool in tools.values()]

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        if self._tool_schemas is None:
            return []
        return self._tool_schemas

    @property
    def hooks(self) -> HookManager:
        return self._hooks

    async def run(self, state: AgentState, metadata: Optional[dict[str, Any]] = None) -> str:
        state.reset_for_run()
        state.max_steps = self._config.max_steps

        ctx = HookContext(state=state, step=0)
        await self._hooks.trigger_before_run(ctx)

        while state.current_step < self._config.max_steps:
            state.increment_step()
            ctx.step = state.current_step

            result = await self._execute_step(state, metadata)

            step_data = {"completed": result.completed, "content": result.content, "error": result.error}
            await self._hooks.trigger_on_step(ctx, step_data)

            if result.completed:
                state.mark_completed()
                await self._events.emit(AgentEvent(
                    type=EventType.COMPLETION,
                    step=state.current_step,
                    data={
                        "message": result.content,
                        "total_steps": state.current_step,
                        "total_input_tokens": state.total_input_tokens,
                        "total_output_tokens": state.total_output_tokens,
                    },
                ))
                await self._hooks.trigger_after_run(ctx, result.content, True)
                return result.content

            if result.waiting_input:
                await self._hooks.trigger_after_run(ctx, "Waiting for user input", True)
                return "Waiting for user input"

            if result.error:
                state.mark_error(result.error)
                await self._events.emit(AgentEvent(
                    type=EventType.ERROR,
                    step=state.current_step,
                    data={"message": result.error},
                ))
                await self._hooks.trigger_after_run(ctx, result.error, False)
                return result.error

        error_msg = f"Task couldn't be completed after {self._config.max_steps} steps."
        state.mark_error(error_msg)
        await self._events.emit(AgentEvent(
            type=EventType.ERROR,
            step=state.current_step,
            data={"message": error_msg, "reason": "max_steps_reached"},
        ))
        await self._hooks.trigger_after_run(ctx, error_msg, False)
        return error_msg

    async def run_stream(
        self,
        state: AgentState,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        state.reset_for_run()
        state.max_steps = self._config.max_steps

        ctx = HookContext(state=state, step=0)
        await self._hooks.trigger_before_run(ctx)

        while state.current_step < self._config.max_steps:
            state.increment_step()
            ctx.step = state.current_step

            async for event in self._execute_step_stream(state, metadata):
                yield event

                if event["type"] == "done":
                    state.mark_completed()
                    await self._hooks.trigger_after_run(ctx, event["data"].get("message", ""), True)
                    return

                if event["type"] == "user_input_required":
                    await self._hooks.trigger_after_run(ctx, "Waiting for user input", True)
                    return

                if event["type"] == "error":
                    state.mark_error(event["data"].get("message", "Unknown error"))
                    await self._hooks.trigger_after_run(ctx, event["data"].get("message", ""), False)
                    return

        error_msg = f"Task couldn't be completed after {self._config.max_steps} steps."
        await self._hooks.trigger_after_run(ctx, error_msg, False)
        yield {
            "type": "error",
            "data": {"message": error_msg, "reason": "max_steps_reached"},
        }

    async def _execute_step(
        self,
        state: AgentState,
        metadata: Optional[dict[str, Any]],
    ) -> StepResult:
        current_tokens = self._token_manager.estimate_tokens(state.messages)
        state.messages = await self._token_manager.maybe_summarize_messages(state.messages)

        await self._events.emit(AgentEvent(
            type=EventType.STEP_START,
            step=state.current_step,
            data={
                "tokens": current_tokens,
                "token_limit": self._token_manager.token_limit,
                "max_steps": self._config.max_steps,
            },
        ))

        try:
            response = await self._llm.generate(
                messages=state.messages,
                tools=self._tool_schemas,
                metadata=metadata,
            )
        except Exception as e:
            return StepResult(error=f"LLM call failed: {str(e)}")

        if response.usage:
            state.add_tokens(response.usage.input_tokens, response.usage.output_tokens)

        await self._events.emit(AgentEvent(
            type=EventType.LLM_RESPONSE,
            step=state.current_step,
            data={
                "content": response.content,
                "thinking": response.thinking,
                "has_tool_calls": bool(response.tool_calls),
                "tool_count": len(response.tool_calls) if response.tool_calls else 0,
                "input_tokens": response.usage.input_tokens if response.usage else 0,
                "output_tokens": response.usage.output_tokens if response.usage else 0,
            },
        ))

        assistant_msg = Message(
            role="assistant",
            content=response.content,
            thinking=response.thinking,
            tool_calls=response.tool_calls,
        )
        state.messages.append(assistant_msg)

        if not response.tool_calls:
            return StepResult(completed=True, content=response.content)

        for tool_call in response.tool_calls:
            if is_user_input_tool_call(tool_call.function.name):
                input_fields = parse_user_input_fields(tool_call.function.arguments)
                request = UserInputRequest(
                    tool_call_id=tool_call.id,
                    fields=[
                        UserInputField(
                            field_name=f.field_name,
                            field_type=f.field_type,
                            field_description=f.field_description,
                        )
                        for f in input_fields
                    ],
                    context=tool_call.function.arguments.get("context"),
                )
                state.mark_waiting_input(request, tool_call.id)

                await self._events.emit(AgentEvent(
                    type=EventType.USER_INPUT_REQUIRED,
                    step=state.current_step,
                    data={
                        "tool_call_id": tool_call.id,
                        "fields": [f.model_dump() for f in input_fields],
                        "context": tool_call.function.arguments.get("context"),
                    },
                ))

                ckpt_config = self._config.checkpoint
                if self.checkpoint_enabled and ckpt_config and ckpt_config.save_on_user_input:
                    await self._save_checkpoint(
                        state,
                        trigger="user_input_wait",
                        pending_tool_calls=[tool_call],
                    )

                return StepResult(waiting_input=True)

        tool_calls_data = [
            (tc.id, tc.function.name, tc.function.arguments)
            for tc in response.tool_calls
        ]

        for call_id, name, args in tool_calls_data:
            await self._events.emit(AgentEvent(
                type=EventType.TOOL_START,
                step=state.current_step,
                data={"tool": name, "arguments": args, "tool_call_id": call_id},
            ))

        results = await self._tool_executor.execute_batch(tool_calls_data)

        for exec_result in results:
            await self._events.emit(AgentEvent(
                type=EventType.TOOL_END,
                step=state.current_step,
                data={
                    "tool": exec_result.tool_name,
                    "tool_call_id": exec_result.tool_call_id,
                    "success": exec_result.result.success,
                    "content": exec_result.result.content if exec_result.result.success else None,
                    "error": exec_result.result.error if not exec_result.result.success else None,
                    "execution_time": exec_result.execution_time,
                },
            ))

            tool_content = (
                exec_result.result.content
                if exec_result.result.success
                else f"Error: {exec_result.result.error}"
            )
            state.messages.append(Message(
                role="tool",
                content=tool_content,
                tool_call_id=exec_result.tool_call_id,
                name=exec_result.tool_name,
            ))

        await self._events.emit(AgentEvent(
            type=EventType.STEP_END,
            step=state.current_step,
            data={"tools_executed": len(results)},
        ))

        ckpt_config = self._config.checkpoint
        if self.checkpoint_enabled and ckpt_config and ckpt_config.save_on_tool_execution:
            await self._save_checkpoint(state, trigger="tool_execution")

        return StepResult()

    async def _execute_step_stream(
        self,
        state: AgentState,
        metadata: Optional[dict[str, Any]],
    ) -> AsyncIterator[dict[str, Any]]:
        current_tokens = self._token_manager.estimate_tokens(state.messages)
        state.messages = await self._token_manager.maybe_summarize_messages(state.messages)

        yield {
            "type": "step",
            "data": {
                "step": state.current_step,
                "max_steps": self._config.max_steps,
                "tokens": current_tokens,
                "token_limit": self._token_manager.token_limit,
            },
        }

        thinking_buffer = ""
        content_buffer = ""
        tool_calls_buffer = []

        try:
            async for event in self._llm.generate_stream(
                messages=state.messages,
                tools=self._tool_schemas,
                metadata=metadata,
            ):
                event_type = event.get("type")

                if event_type == "thinking_delta":
                    delta = event.get("delta", "")
                    thinking_buffer += delta
                    yield {"type": "thinking", "data": {"delta": delta}}

                elif event_type == "content_delta":
                    delta = event.get("delta", "")
                    content_buffer += delta
                    yield {"type": "content", "data": {"delta": delta}}

                elif event_type == "tool_use":
                    tool_call = event.get("tool_call")
                    if tool_call:
                        tool_calls_buffer.append(tool_call)
                        yield {
                            "type": "tool_call",
                            "data": {
                                "tool": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }

                elif event_type == "done":
                    response = event.get("response")
                    if response and response.usage:
                        state.add_tokens(response.usage.input_tokens, response.usage.output_tokens)
                    break

        except Exception as e:
            yield {"type": "error", "data": {"message": f"LLM call failed: {str(e)}"}}
            return

        assistant_msg = Message(
            role="assistant",
            content=content_buffer,
            thinking=thinking_buffer if thinking_buffer else None,
            tool_calls=tool_calls_buffer if tool_calls_buffer else None,
        )
        state.messages.append(assistant_msg)

        if not tool_calls_buffer:
            yield {
                "type": "done",
                "data": {"message": content_buffer, "steps": state.current_step, "reason": "completed"},
            }
            return

        for tool_call in tool_calls_buffer:
            if is_user_input_tool_call(tool_call.function.name):
                input_fields = parse_user_input_fields(tool_call.function.arguments)
                request = UserInputRequest(
                    tool_call_id=tool_call.id,
                    fields=[
                        UserInputField(
                            field_name=f.field_name,
                            field_type=f.field_type,
                            field_description=f.field_description,
                        )
                        for f in input_fields
                    ],
                    context=tool_call.function.arguments.get("context"),
                )
                state.mark_waiting_input(request, tool_call.id)

                yield {
                    "type": "user_input_required",
                    "data": {
                        "tool_call_id": tool_call.id,
                        "fields": [f.model_dump() for f in input_fields],
                        "context": tool_call.function.arguments.get("context"),
                    },
                }

                ckpt_config = self._config.checkpoint
                if self.checkpoint_enabled and ckpt_config and ckpt_config.save_on_user_input:
                    await self._save_checkpoint(
                        state,
                        trigger="user_input_wait",
                        pending_tool_calls=[tool_call],
                    )

                return

        tool_calls_data = [
            (tc.id, tc.function.name, tc.function.arguments)
            for tc in tool_calls_buffer
        ]
        results = await self._tool_executor.execute_batch(tool_calls_data)

        for exec_result in results:
            yield {
                "type": "tool_result",
                "data": {
                    "tool": exec_result.tool_name,
                    "success": exec_result.result.success,
                    "content": exec_result.result.content if exec_result.result.success else None,
                    "error": exec_result.result.error if not exec_result.result.success else None,
                    "execution_time": exec_result.execution_time,
                },
            }

            tool_content = (
                exec_result.result.content
                if exec_result.result.success
                else f"Error: {exec_result.result.error}"
            )
            state.messages.append(Message(
                role="tool",
                content=tool_content,
                tool_call_id=exec_result.tool_call_id,
                name=exec_result.tool_name,
            ))

        ckpt_config = self._config.checkpoint
        if self.checkpoint_enabled and ckpt_config and ckpt_config.save_on_tool_execution:
            await self._save_checkpoint(state, trigger="tool_execution")

    async def resume_from_input(
        self,
        state: AgentState,
        user_response: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        if not state.is_waiting_input or not state.paused_tool_call_id:
            return "Agent is not waiting for user input"

        tool_msg = Message(
            role="tool",
            content=str(user_response),
            tool_call_id=state.paused_tool_call_id,
            name="get_user_input",
        )
        state.messages.append(tool_msg)
        state.resume_from_input()

        return await self.run(state, metadata)

    async def resume_from_input_stream(
        self,
        state: AgentState,
        user_response: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        if not state.is_waiting_input or not state.paused_tool_call_id:
            yield {"type": "error", "data": {"message": "Agent is not waiting for user input"}}
            return

        tool_msg = Message(
            role="tool",
            content=str(user_response),
            tool_call_id=state.paused_tool_call_id,
            name="get_user_input",
        )
        state.messages.append(tool_msg)
        state.resume_from_input()

        async for event in self.run_stream(state, metadata):
            yield event

    async def resume_from_checkpoint(
        self,
        checkpoint_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> tuple[AgentState, str]:
        if not self.checkpoint_enabled:
            raise RuntimeError("Checkpoint is not enabled")

        config = self._config.checkpoint
        assert config is not None
        storage = config.get_storage()

        checkpoint: Optional[Checkpoint] = None
        if checkpoint_id:
            checkpoint = await storage.load(checkpoint_id)
        elif thread_id:
            checkpoint = await storage.load_latest(thread_id)

        if checkpoint is None:
            raise ValueError(f"Checkpoint not found: checkpoint_id={checkpoint_id}, thread_id={thread_id}")

        state = AgentState.from_checkpoint(checkpoint, max_steps=self._config.max_steps)
        state.resume_from_checkpoint()

        result = await self.run(state, metadata)
        return state, result

    async def resume_from_checkpoint_stream(
        self,
        checkpoint_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> tuple[AgentState, AsyncIterator[dict[str, Any]]]:
        if not self.checkpoint_enabled:
            raise RuntimeError("Checkpoint is not enabled")

        config = self._config.checkpoint
        assert config is not None
        storage = config.get_storage()

        checkpoint: Optional[Checkpoint] = None
        if checkpoint_id:
            checkpoint = await storage.load(checkpoint_id)
        elif thread_id:
            checkpoint = await storage.load_latest(thread_id)

        if checkpoint is None:
            raise ValueError(f"Checkpoint not found: checkpoint_id={checkpoint_id}, thread_id={thread_id}")

        state = AgentState.from_checkpoint(checkpoint, max_steps=self._config.max_steps)
        state.resume_from_checkpoint()

        async def stream_generator() -> AsyncIterator[dict[str, Any]]:
            async for event in self.run_stream(state, metadata):
                yield event

        return state, stream_generator()


class Agent:
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

    @property
    def hooks(self) -> HookManager:
        return self._loop.hooks

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
