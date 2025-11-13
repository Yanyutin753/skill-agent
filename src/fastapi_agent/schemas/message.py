"""Message and response schemas."""

from typing import Any, Optional, List
from pydantic import BaseModel, Field


class FunctionCall(BaseModel):
    """Function call within a tool call."""
    name: str
    arguments: dict[str, Any]


class ToolCall(BaseModel):
    """Tool call from LLM."""
    id: str
    type: str = "function"
    function: FunctionCall


class Message(BaseModel):
    """Message in conversation history."""
    role: str  # system, user, assistant, tool
    content: str | list[dict[str, Any]]
    thinking: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class LLMResponse(BaseModel):
    """Response from LLM."""
    content: str
    thinking: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: str = "stop"


class AgentRequest(BaseModel):
    """Request to agent endpoint."""
    message: str = Field(..., description="User message/task")
    workspace_dir: Optional[str] = Field(None, description="Workspace directory path")
    max_steps: Optional[int] = Field(50, description="Maximum execution steps")


class AgentResponse(BaseModel):
    """Response from agent endpoint."""
    success: bool
    message: str
    steps: int
    logs: List[dict[str, Any]] = []
