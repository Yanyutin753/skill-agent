"""Agent event system for decoupled component communication."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable


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
