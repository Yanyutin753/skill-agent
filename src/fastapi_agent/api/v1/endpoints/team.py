"""
Team API endpoints for multi-agent coordination.

Uses the Team system where a Leader agent intelligently delegates tasks to members.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends

from fastapi_agent.core.team import Team
from fastapi_agent.schemas.team import (
    TeamConfig,
    TeamMemberConfig,
    TeamRunResponse as TeamRunResponseSchema,
)
from fastapi_agent.api.deps import get_llm_client, get_tools
from fastapi_agent.utils.logger import logger

router = APIRouter(prefix="/team", tags=["team"])


# Predefined role configurations
ROLE_CONFIGS = {
    "researcher": {
        "role": "Research Specialist",
        "instructions": "你是研究员，擅长搜索信息、阅读资料并总结要点。专注于收集准确、全面的信息。",
        "tools": ["read", "bash"]
    },
    "writer": {
        "role": "Writing Expert",
        "instructions": "你是写作专家，擅长将信息组织成清晰、结构化的文档。注重内容的逻辑性和可读性。",
        "tools": ["write", "edit"]
    },
    "coder": {
        "role": "Programming Expert",
        "instructions": "你是编程专家，擅长编写代码和解决技术问题。注重代码质量和最佳实践。",
        "tools": ["write", "edit", "read", "bash"]
    },
    "reviewer": {
        "role": "Quality Reviewer",
        "instructions": "你是审阅专家，负责检查内容的质量、准确性和完整性。提供建设性的反馈。",
        "tools": ["read"]
    },
    "analyst": {
        "role": "Data Analyst",
        "instructions": "你是数据分析专家，擅长分析数据、提取洞察并生成报告。",
        "tools": []  # Will get all tools
    }
}


class TeamRunRequest(BaseModel):
    """Team run request"""
    message: str = Field(..., description="任务描述")
    members: List[str] = Field(
        default=["researcher", "writer"],
        description="成员角色列表: researcher, writer, coder, reviewer, analyst"
    )
    delegate_to_all: bool = Field(
        default=False,
        description="是否将任务广播给所有成员（而不是由 Leader 选择性委派）"
    )
    team_name: Optional[str] = Field(default="AI Team", description="团队名称")
    team_description: Optional[str] = Field(default=None, description="团队描述")
    leader_instructions: Optional[str] = Field(default=None, description="Leader 的额外指令")
    workspace_dir: Optional[str] = Field(default="./workspace", description="工作空间目录")
    max_steps: int = Field(default=50, description="最大执行步数")
    session_id: Optional[str] = Field(default=None, description="会话ID（用于多轮对话）")


class TeamRunResponse(BaseModel):
    """Team run response"""
    success: bool
    team_name: str
    message: str
    member_runs: List[Dict[str, Any]] = Field(default_factory=list)
    total_steps: int = 0
    iterations: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _build_team_config(
    request: TeamRunRequest,
    available_tools: List
) -> TeamConfig:
    """Build TeamConfig from request and available tools."""

    # Get all tool names for filtering
    all_tool_names = [getattr(t, 'name', '') for t in available_tools]

    # Build member configs
    members = []
    for role_name in request.members:
        role_config = ROLE_CONFIGS.get(role_name.lower())

        if role_config:
            # Filter tools that exist in available_tools
            if role_config["tools"]:
                member_tools = [t for t in role_config["tools"] if t in all_tool_names]
            else:
                # Empty list means all tools (for analyst)
                member_tools = all_tool_names

            members.append(TeamMemberConfig(
                name=role_name.capitalize(),
                role=role_config["role"],
                instructions=role_config["instructions"],
                tools=member_tools
            ))
        else:
            # Custom role
            members.append(TeamMemberConfig(
                name=role_name.capitalize(),
                role=role_name,
                instructions=f"你是{role_name}，请协助完成任务。",
                tools=all_tool_names  # Give all tools to custom roles
            ))

    return TeamConfig(
        name=request.team_name or "AI Team",
        description=request.team_description,
        members=members,
        leader_instructions=request.leader_instructions,
        delegate_to_all=request.delegate_to_all
    )


@router.post("/run", response_model=TeamRunResponse)
async def run_team(
    request: TeamRunRequest,
    llm_client=Depends(get_llm_client),
    tools=Depends(get_tools)
) -> TeamRunResponse:
    """
    Execute a multi-agent team task.

    The Team system uses a Leader agent that intelligently analyzes the task
    and delegates work to appropriate team members.

    **How it works:**
    1. Leader receives the task and analyzes what needs to be done
    2. Leader uses delegation tools to assign work to members
    3. Members execute their tasks and return results
    4. Leader synthesizes results and provides final answer

    **Delegation modes:**
    - `delegate_to_all=false` (default): Leader chooses which member(s) to delegate to
    - `delegate_to_all=true`: Task is sent to all members for diverse perspectives

    **Available roles:**
    - `researcher`: Information gathering and research
    - `writer`: Content creation and documentation
    - `coder`: Programming and technical tasks
    - `reviewer`: Quality review and feedback
    - `analyst`: Data analysis and insights

    **Example:**
    ```json
    {
        "message": "Research Python async programming and write a technical article",
        "members": ["researcher", "writer", "reviewer"],
        "delegate_to_all": false
    }
    ```
    """
    try:
        if not request.members:
            raise HTTPException(status_code=400, detail="At least one member is required")

        # Build team configuration
        team_config = _build_team_config(request, tools)

        # Create team
        team = Team(
            config=team_config,
            llm_client=llm_client,
            available_tools=tools,
            workspace_dir=request.workspace_dir or "./workspace"
        )

        # Execute task
        logger.info(f"Running team '{team_config.name}' with members={request.members}")
        result: TeamRunResponseSchema = await team.run(
            message=request.message,
            max_steps=request.max_steps,
            session_id=request.session_id
        )

        # Convert to response
        return TeamRunResponse(
            success=result.success,
            team_name=result.team_name,
            message=result.message,
            member_runs=[mr.model_dump() for mr in result.member_runs],
            total_steps=result.total_steps,
            iterations=result.iterations,
            metadata=result.metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Team run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roles")
async def list_roles() -> Dict[str, Any]:
    """
    List available team member roles.

    Returns information about each predefined role and their capabilities.
    """
    return {
        "roles": [
            {
                "name": name,
                "role": config["role"],
                "description": config["instructions"],
                "default_tools": config["tools"] if config["tools"] else ["all"]
            }
            for name, config in ROLE_CONFIGS.items()
        ],
        "note": "You can also use custom role names. Custom roles will have access to all tools."
    }


@router.get("/health")
async def team_health() -> Dict[str, str]:
    """Health check for team endpoints"""
    return {"status": "healthy", "service": "team"}
