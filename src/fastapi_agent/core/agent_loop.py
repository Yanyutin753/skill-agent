"""Core agent execution loop with event-driven architecture."""

from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional
from uuid import uuid4

from fastapi_agent.core.agent_events import EventEmitter, EventType, AgentEvent
from fastapi_agent.core.agent_state import AgentState, AgentStatus
from fastapi_agent.core.checkpoint import Checkpoint, CheckpointConfig, CheckpointStorage
from fastapi_agent.core.tool_executor import ToolExecutor
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.token_manager import TokenManager
from fastapi_agent.schemas.message import Message, UserInputRequest, UserInputField, ToolCall
from fastapi_agent.tools.base import Tool
from fastapi_agent.tools.user_input_tool import is_user_input_tool_call, parse_user_input_fields


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

    async def run(
        self,
        state: AgentState,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        state.reset_for_run()
        state.max_steps = self._config.max_steps

        while state.current_step < self._config.max_steps:
            state.increment_step()

            result = await self._execute_step(state, metadata)

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
                return result.content

            if result.waiting_input:
                return "Waiting for user input"

            if result.error:
                state.mark_error(result.error)
                await self._events.emit(AgentEvent(
                    type=EventType.ERROR,
                    step=state.current_step,
                    data={"message": result.error},
                ))
                return result.error

        error_msg = f"Task couldn't be completed after {self._config.max_steps} steps."
        state.mark_error(error_msg)
        await self._events.emit(AgentEvent(
            type=EventType.ERROR,
            step=state.current_step,
            data={"message": error_msg, "reason": "max_steps_reached"},
        ))
        return error_msg

    async def run_stream(
        self,
        state: AgentState,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        state.reset_for_run()
        state.max_steps = self._config.max_steps

        while state.current_step < self._config.max_steps:
            state.increment_step()

            async for event in self._execute_step_stream(state, metadata):
                yield event

                if event["type"] == "done":
                    state.mark_completed()
                    return

                if event["type"] == "user_input_required":
                    return

                if event["type"] == "error":
                    state.mark_error(event["data"].get("message", "Unknown error"))
                    return

        yield {
            "type": "error",
            "data": {
                "message": f"Task couldn't be completed after {self._config.max_steps} steps.",
                "reason": "max_steps_reached",
            },
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
                        state.add_tokens(
                            response.usage.input_tokens,
                            response.usage.output_tokens,
                        )
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
                "data": {
                    "message": content_buffer,
                    "steps": state.current_step,
                    "reason": "completed",
                },
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
            raise ValueError(
                f"Checkpoint not found: checkpoint_id={checkpoint_id}, thread_id={thread_id}"
            )

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
            raise ValueError(
                f"Checkpoint not found: checkpoint_id={checkpoint_id}, thread_id={thread_id}"
            )

        state = AgentState.from_checkpoint(checkpoint, max_steps=self._config.max_steps)
        state.resume_from_checkpoint()

        async def stream_generator() -> AsyncIterator[dict[str, Any]]:
            async for event in self.run_stream(state, metadata):
                yield event

        return state, stream_generator()
