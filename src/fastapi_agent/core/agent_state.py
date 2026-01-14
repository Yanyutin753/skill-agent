"""Agent state management for tracking execution context."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from fastapi_agent.schemas.message import Message, UserInputRequest, UserInputField


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

    def mark_waiting_input(
        self,
        request: UserInputRequest,
        tool_call_id: str,
    ) -> None:
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
        from fastapi_agent.core.checkpoint import Checkpoint
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
    def from_checkpoint(
        cls,
        checkpoint: "Checkpoint",
        max_steps: int = 50,
    ) -> "AgentState":
        from fastapi_agent.core.checkpoint import Checkpoint as CkptClass
        state = cls(
            status=AgentStatus(checkpoint.status),
            current_step=checkpoint.step,
            max_steps=max_steps,
            total_input_tokens=checkpoint.token_usage.get("input", 0),
            total_output_tokens=checkpoint.token_usage.get("output", 0),
            messages=checkpoint.get_messages(),
            last_checkpoint_id=checkpoint.id,
            thread_id=checkpoint.thread_id,
        )
        return state
