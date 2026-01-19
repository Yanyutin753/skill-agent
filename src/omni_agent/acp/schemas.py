"""ACP（Agent 客户端协议）数据模式。

基于 Zed 的 Agent 客户端协议：
- 协议规范：https://agentclientprotocol.com/
- Schema：https://github.com/zed-industries/agent-client-protocol/blob/main/schema/schema.json
"""

from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel, Field


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[int, str]] = None
    method: str
    params: Optional[dict[str, Any]] = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[int, str]] = None
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None


class FsCapabilities(BaseModel):
    read_text_file: bool = Field(False, alias="readTextFile")
    write_text_file: bool = Field(False, alias="writeTextFile")

    class Config:
        populate_by_name = True


class ClientCapabilities(BaseModel):
    fs: Optional[FsCapabilities] = None
    terminal: bool = False


class PromptCapabilities(BaseModel):
    image: bool = False
    audio: bool = False
    embedded_context: bool = Field(False, alias="embeddedContext")

    class Config:
        populate_by_name = True


class McpCapabilities(BaseModel):
    http: bool = False
    sse: bool = False
    stdio: bool = False


class AgentCapabilities(BaseModel):
    load_session: bool = Field(False, alias="loadSession")
    prompt_capabilities: Optional[PromptCapabilities] = Field(None, alias="promptCapabilities")
    mcp: Optional[McpCapabilities] = None

    class Config:
        populate_by_name = True


class AgentInfo(BaseModel):
    name: str
    title: Optional[str] = None
    version: Optional[str] = None


class InitializeRequest(BaseModel):
    protocol_version: str = Field(..., alias="protocolVersion")
    client_info: Optional[dict[str, str]] = Field(None, alias="clientInfo")
    client_capabilities: Optional[ClientCapabilities] = Field(None, alias="clientCapabilities")

    class Config:
        populate_by_name = True


class InitializeResponse(BaseModel):
    protocol_version: int = Field(1, alias="protocolVersion")
    agent_capabilities: AgentCapabilities = Field(default_factory=lambda: AgentCapabilities(), alias="agentCapabilities")
    agent_info: AgentInfo = Field(..., alias="agentInfo")
    auth_methods: list[str] = Field(default_factory=list, alias="authMethods")

    class Config:
        populate_by_name = True


class McpServer(BaseModel):
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None


class SessionNewRequest(BaseModel):
    cwd: str
    mcp_servers: list[McpServer] = Field(default_factory=list, alias="mcpServers")

    class Config:
        populate_by_name = True


class SessionMode(BaseModel):
    id: str
    name: str
    description: Optional[str] = None


class SessionModeState(BaseModel):
    current_mode_id: str = Field(..., alias="currentModeId")
    available_modes: list[SessionMode] = Field(default_factory=list, alias="availableModes")

    class Config:
        populate_by_name = True


class SessionNewResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    modes: Optional[SessionModeState] = None

    class Config:
        populate_by_name = True


class ContentBlockType(str, Enum):
    TEXT = "text"
    RESOURCE = "resource"
    RESOURCE_LINK = "resourceLink"
    IMAGE = "image"


class TextContent(BaseModel):
    type: str = "text"
    text: str
    annotations: Optional[Any] = None


class ResourceContent(BaseModel):
    uri: str
    text: Optional[str] = None
    mime_type: Optional[str] = Field(None, alias="mimeType")

    class Config:
        populate_by_name = True


class ResourceBlock(BaseModel):
    type: str = "resource"
    resource: ResourceContent


class ResourceLinkBlock(BaseModel):
    type: str = "resourceLink"
    uri: str
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    mime_type: Optional[str] = Field(None, alias="mimeType")

    class Config:
        populate_by_name = True


ContentBlock = Union[TextContent, ResourceBlock, ResourceLinkBlock]


class SessionPromptRequest(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    prompt: list[ContentBlock]

    class Config:
        populate_by_name = True


class StopReason(str, Enum):
    END_TURN = "endoftext"
    END_OF_TEXT = "endoftext"
    STOP_SEQUENCE = "stopsequence"
    TOOL_ERROR = "tool_error"
    CANCELLED = "cancelled"
    ERROR = "error"


class SessionPromptResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    response: dict[str, Any] = Field(default_factory=lambda: {"stopReason": "endoftext"})

    class Config:
        populate_by_name = True


class ToolKind(str, Enum):
    READ = "read"
    EDIT = "edit"
    DELETE = "delete"
    MOVE = "move"
    SEARCH = "search"
    EXECUTE = "execute"
    THINK = "think"
    FETCH = "fetch"
    OTHER = "other"


class ToolCallStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ERROR = "error"


class ToolCallLocation(BaseModel):
    path: str
    line: Optional[int] = None


class DiffContent(BaseModel):
    type: str = "diff"
    path: str
    old_text: Optional[str] = Field(None, alias="oldText")
    new_text: str = Field(..., alias="newText")

    class Config:
        populate_by_name = True


class ToolCallContent(BaseModel):
    type: str = "content"
    content: ContentBlock


class ToolCall(BaseModel):
    tool_call_id: str = Field(..., alias="toolCallId")
    title: str
    kind: Optional[ToolKind] = None
    status: Optional[ToolCallStatus] = None
    content: list[Union[ToolCallContent, DiffContent]] = Field(default_factory=list)
    locations: list[ToolCallLocation] = Field(default_factory=list)
    raw_input: Optional[dict[str, Any]] = Field(None, alias="rawInput")
    raw_output: Optional[Any] = Field(None, alias="rawOutput")

    class Config:
        populate_by_name = True


class ToolCallUpdate(BaseModel):
    tool_call_id: str = Field(..., alias="toolCallId")
    status: Optional[ToolCallStatus] = None
    content: Optional[list[Union[ToolCallContent, DiffContent]]] = None
    title: Optional[str] = None
    kind: Optional[ToolKind] = None
    locations: Optional[list[ToolCallLocation]] = None
    raw_input: Optional[dict[str, Any]] = Field(None, alias="rawInput")
    raw_output: Optional[Any] = Field(None, alias="rawOutput")

    class Config:
        populate_by_name = True


class PlanEntryStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanEntryPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PlanEntry(BaseModel):
    content: str
    status: PlanEntryStatus = PlanEntryStatus.PENDING
    priority: PlanEntryPriority = PlanEntryPriority.MEDIUM


class Plan(BaseModel):
    entries: list[PlanEntry] = Field(default_factory=list)


class ContentChunk(BaseModel):
    content: ContentBlock


class SessionUpdateType(str, Enum):
    AGENT_THOUGHT_CHUNK = "agent_thought_chunk"
    AGENT_MESSAGE_CHUNK = "agent_message_chunk"
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    TOOL_CALL_UPDATE = "tool_call_update"


class SessionUpdate(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    update: dict[str, Any]

    class Config:
        populate_by_name = True

    @classmethod
    def thought_chunk(cls, session_id: str, text: str) -> "SessionUpdate":
        return cls(
            sessionId=session_id,
            update={
                "sessionUpdate": SessionUpdateType.AGENT_THOUGHT_CHUNK.value,
                "content": {"type": "text", "text": text},
            },
        )

    @classmethod
    def message_chunk(cls, session_id: str, text: str) -> "SessionUpdate":
        return cls(
            sessionId=session_id,
            update={
                "sessionUpdate": SessionUpdateType.AGENT_MESSAGE_CHUNK.value,
                "content": {"type": "text", "text": text},
            },
        )

    @classmethod
    def plan(cls, session_id: str, plan: Plan) -> "SessionUpdate":
        return cls(
            sessionId=session_id,
            update={
                "sessionUpdate": SessionUpdateType.PLAN.value,
                "entries": [e.model_dump() for e in plan.entries],
            },
        )

    @classmethod
    def tool_call(cls, session_id: str, tool: ToolCall) -> "SessionUpdate":
        return cls(
            sessionId=session_id,
            update={
                "sessionUpdate": SessionUpdateType.TOOL_CALL.value,
                **tool.model_dump(by_alias=True, exclude_none=True),
            },
        )

    @classmethod
    def tool_call_update(cls, session_id: str, update: ToolCallUpdate) -> "SessionUpdate":
        return cls(
            sessionId=session_id,
            update={
                "sessionUpdate": SessionUpdateType.TOOL_CALL_UPDATE.value,
                **update.model_dump(by_alias=True, exclude_none=True),
            },
        )
