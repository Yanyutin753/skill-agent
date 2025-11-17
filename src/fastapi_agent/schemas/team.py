"""Team schemas for multi-agent collaboration."""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class TeamMemberConfig(BaseModel):
    """Configuration for a team member."""

    name: str = Field(..., description="Team member name")
    role: str = Field(..., description="Team member role/specialty")
    instructions: Optional[str] = Field(None, description="Specific instructions for this member")
    tools: Optional[List[str]] = Field(default_factory=list, description="Tools available to this member")
    model: Optional[str] = Field(None, description="LLM model for this member (defaults to team model)")


class TeamConfig(BaseModel):
    """Configuration for a team of agents."""

    name: str = Field(..., description="Team name")
    description: Optional[str] = Field(None, description="Team description")
    members: List[TeamMemberConfig] = Field(..., description="Team members")
    model: Optional[str] = Field("openai:gpt-4o-mini", description="Default model for the team")
    leader_instructions: Optional[str] = Field(
        None,
        description="Instructions for the team leader on how to delegate tasks"
    )
    delegate_to_all: bool = Field(
        False,
        description="If True, delegate tasks to all members instead of selecting specific ones"
    )
    max_iterations: int = Field(
        10,
        description="Maximum number of delegation iterations"
    )


class TeamRunRequest(BaseModel):
    """Request to run a team."""

    message: str = Field(..., description="User message/task")
    team_config: Optional[TeamConfig] = Field(None, description="Team configuration (if creating new team)")
    team_id: Optional[str] = Field(None, description="Existing team ID to use")
    workspace_dir: Optional[str] = Field("./workspace", description="Workspace directory")
    max_steps: int = Field(50, description="Max steps per agent")
    stream: bool = Field(False, description="Whether to stream responses")


class MemberRunResult(BaseModel):
    """Result from a team member run."""

    member_name: str
    member_role: str
    task: str
    response: str
    success: bool
    error: Optional[str] = None
    steps: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TeamRunResponse(BaseModel):
    """Response from team run."""

    success: bool
    team_name: str
    message: str
    member_runs: List[MemberRunResult] = Field(default_factory=list)
    total_steps: int = 0
    iterations: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
