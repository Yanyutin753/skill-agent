"""Team orchestration for multi-agent collaboration."""

import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.session import RunRecord, TeamSession, TeamSessionManager
from fastapi_agent.schemas.team import TeamConfig, TeamMemberConfig, MemberRunResult, TeamRunResponse
from fastapi_agent.tools.base import Tool


class DelegateTaskTool(Tool):
    """Tool for delegating tasks to team members."""

    def __init__(self, team: "Team", session_id: Optional[str] = None):
        self.team = team
        self.session_id = session_id

    @property
    def name(self) -> str:
        return "delegate_task_to_member"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to a specific team member. "
            "Use this to assign work to the team member best suited for the task."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        # Build member choices from team
        member_enum = [m.name for m in self.team.config.members]

        return {
            "type": "object",
            "properties": {
                "member_name": {
                    "type": "string",
                    "enum": member_enum,
                    "description": f"Name of the team member to delegate to. Available members: {', '.join(member_enum)}"
                },
                "task": {
                    "type": "string",
                    "description": "Clear description of the task to delegate"
                }
            },
            "required": ["member_name", "task"]
        }

    def execute(self, member_name: str, task: str) -> str:
        """Execute task delegation."""
        # Find the member
        member_config = None
        for m in self.team.config.members:
            if m.name == member_name:
                member_config = m
                break

        if not member_config:
            return f"Error: Member '{member_name}' not found in team"

        # Run the member agent (with session tracking)
        result = self.team._run_member(member_config, task, session_id=self.session_id)

        # Format response
        if result.success:
            return f"✓ {member_name} completed task:\n{result.response}"
        else:
            return f"✗ {member_name} failed: {result.error}"


class DelegateToAllTool(Tool):
    """Tool for delegating tasks to all team members."""

    def __init__(self, team: "Team", session_id: Optional[str] = None):
        self.team = team
        self.session_id = session_id

    @property
    def name(self) -> str:
        return "delegate_task_to_all_members"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to ALL team members to get diverse perspectives. "
            "Use this when you need collaborative input from the entire team."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task description to send to all members"
                }
            },
            "required": ["task"]
        }

    def execute(self, task: str) -> str:
        """Execute task delegation to all members."""
        results = []
        for member_config in self.team.config.members:
            result = self.team._run_member(member_config, task, session_id=self.session_id)
            if result.success:
                results.append(f"✓ {member_config.name}: {result.response}")
            else:
                results.append(f"✗ {member_config.name}: {result.error}")

        return "\n\n".join(results)


class Team:
    """Team of agents that can collaborate on tasks."""

    def __init__(
        self,
        config: TeamConfig,
        llm_client: LLMClient,
        available_tools: Optional[List[Tool]] = None,
        workspace_dir: str = "./workspace",
        session_manager: Optional[TeamSessionManager] = None
    ):
        self.config = config
        self.llm_client = llm_client
        self.available_tools = available_tools or []
        self.workspace_dir = workspace_dir
        self.team_id = str(uuid4())
        self.session_manager = session_manager or TeamSessionManager()

        # Track member runs (for current execution)
        self.member_runs: List[MemberRunResult] = []
        self.iteration_count = 0
        self._current_run_id: Optional[str] = None  # Track current leader run ID

    def _get_leader_tools(self, session_id: Optional[str] = None) -> List[Tool]:
        """Get tools for the team leader.

        Args:
            session_id: Optional session ID to pass to delegation tools

        Returns:
            List of delegation tools
        """
        if self.config.delegate_to_all:
            return [DelegateToAllTool(self, session_id=session_id)]
        else:
            return [DelegateTaskTool(self, session_id=session_id)]

    def _build_leader_system_prompt(self, history_context: str = "") -> str:
        """Build system prompt for team leader.

        Args:
            history_context: Optional formatted history from previous runs

        Returns:
            Complete system prompt for the leader agent
        """
        members_desc = []
        for member in self.config.members:
            tools_str = ", ".join(member.tools) if member.tools else "No tools"
            members_desc.append(
                f"- **{member.name}** ({member.role})\n"
                f"  Tools: {tools_str}\n"
                f"  {member.instructions or 'General purpose agent'}"
            )

        members_info = "\n".join(members_desc)

        if self.config.delegate_to_all:
            delegation_instructions = """
When you receive a task:
1. Use the `delegate_task_to_all_members` tool to send the task to ALL team members
2. Analyze and synthesize the responses from all members
3. Provide a comprehensive final answer based on the collaborative input
"""
        else:
            delegation_instructions = """
When you receive a task:
1. Analyze which team member(s) are best suited for the task
2. Use the `delegate_task_to_member` tool to assign work to appropriate members
3. You can delegate to multiple members if needed
4. Synthesize the responses and provide a final answer
5. If the member's response is insufficient, you can delegate to another member or ask for clarification
"""

        # Build base prompt
        system_prompt = f"""You are the leader of the {self.config.name} team.

TEAM DESCRIPTION:
{self.config.description or 'A collaborative team of specialized agents'}

TEAM MEMBERS:
{members_info}

YOUR ROLE AS LEADER:
{delegation_instructions}

DELEGATION GUIDELINES:
- Choose members based on their roles and available tools
- Provide clear, specific task descriptions when delegating
- Analyze member responses before providing your final answer
- For simple greetings or questions about the team, respond directly without delegation

{self.config.leader_instructions or ''}
"""

        # Add history context if available
        if history_context:
            system_prompt += f"\n\nPREVIOUS INTERACTIONS:\n{history_context}\n"
            system_prompt += "\nUse the previous interactions to maintain continuity and context.\n"

        return system_prompt

    def _run_member(
        self,
        member_config: TeamMemberConfig,
        task: str,
        session_id: Optional[str] = None
    ) -> MemberRunResult:
        """Run a specific team member on a task.

        Args:
            member_config: Member configuration
            task: Task to execute
            session_id: Optional session ID for recording run

        Returns:
            Member run result
        """
        try:
            # Get tools for this member
            member_tools = []
            if member_config.tools:
                for tool in self.available_tools:
                    if tool.name in member_config.tools:
                        member_tools.append(tool)

            # Create member-specific system prompt
            system_prompt = f"""You are {member_config.name}, a {member_config.role}.

{member_config.instructions or ''}

Focus on your area of expertise and provide clear, actionable responses.
"""

            # Create agent for this member
            member_agent = Agent(
                llm_client=self.llm_client,
                tools=member_tools,
                system_prompt=system_prompt,
                workspace_dir=self.workspace_dir,
                max_steps=10,  # Limit steps for members
                enable_logging=False  # Don't create separate logs for members
            )

            # Run the member
            response = member_agent.run(task)

            result = MemberRunResult(
                member_name=member_config.name,
                member_role=member_config.role,
                task=task,
                response=response.get("message", ""),
                success=response.get("success", False),
                steps=response.get("steps", 0),
                metadata=response
            )

            self.member_runs.append(result)

            # Save to session if session_id provided
            if session_id and self._current_run_id:
                member_run_record = RunRecord(
                    run_id=str(uuid4()),
                    parent_run_id=self._current_run_id,  # Link to leader run
                    runner_type="member",
                    runner_name=member_config.name,
                    task=task,
                    response=result.response,
                    success=result.success,
                    steps=result.steps,
                    timestamp=time.time(),
                    metadata={"role": member_config.role, "response_data": response}
                )
                self.session_manager.add_run(session_id, member_run_record)

            return result

        except Exception as e:
            result = MemberRunResult(
                member_name=member_config.name,
                member_role=member_config.role,
                task=task,
                response="",
                success=False,
                error=str(e),
                steps=0
            )
            self.member_runs.append(result)

            # Save error to session if session_id provided
            if session_id and self._current_run_id:
                member_run_record = RunRecord(
                    run_id=str(uuid4()),
                    parent_run_id=self._current_run_id,
                    runner_type="member",
                    runner_name=member_config.name,
                    task=task,
                    response=f"Error: {str(e)}",
                    success=False,
                    steps=0,
                    timestamp=time.time(),
                    metadata={"role": member_config.role, "error": str(e)}
                )
                self.session_manager.add_run(session_id, member_run_record)

            return result

    def run(
        self,
        message: str,
        max_steps: int = 50,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        num_history_runs: int = 3
    ) -> TeamRunResponse:
        """Run the team on a task.

        Args:
            message: Task message for the team
            max_steps: Maximum execution steps
            session_id: Optional session ID for history tracking
            user_id: Optional user ID for session
            num_history_runs: Number of previous runs to include in context

        Returns:
            TeamRunResponse with execution results
        """
        self.member_runs = []
        self.iteration_count = 0
        self._current_run_id = str(uuid4())  # Generate run ID for this execution

        try:
            # Get session and history if session_id provided
            history_context = ""
            if session_id:
                session = self.session_manager.get_session(
                    session_id=session_id,
                    team_name=self.config.name,
                    user_id=user_id
                )
                history_context = session.get_history_context(num_runs=num_history_runs)

            # Create leader agent with history context
            leader_tools = self._get_leader_tools(session_id=session_id)
            system_prompt = self._build_leader_system_prompt(history_context=history_context)

            leader = Agent(
                llm_client=self.llm_client,
                tools=leader_tools,
                system_prompt=system_prompt,
                workspace_dir=self.workspace_dir,
                max_steps=max_steps,
                enable_logging=True
            )

            # Run the leader
            response = leader.run(message)

            # Calculate total steps
            total_steps = response.get("steps", 0)
            for member_run in self.member_runs:
                total_steps += member_run.steps

            # Save leader run to session if session_id provided
            if session_id:
                leader_run_record = RunRecord(
                    run_id=self._current_run_id,
                    parent_run_id=None,  # Leader has no parent
                    runner_type="team_leader",
                    runner_name=self.config.name,
                    task=message,
                    response=response.get("message", ""),
                    success=response.get("success", False),
                    steps=total_steps,
                    timestamp=time.time(),
                    metadata={
                        "leader_response": response,
                        "member_count": len(self.member_runs)
                    }
                )
                self.session_manager.add_run(session_id, leader_run_record)

            return TeamRunResponse(
                success=response.get("success", False),
                team_name=self.config.name,
                message=response.get("message", ""),
                member_runs=self.member_runs,
                total_steps=total_steps,
                iterations=len(self.member_runs),
                metadata={
                    "leader_response": response,
                    "team_config": self.config.model_dump(),
                    "session_id": session_id,
                    "run_id": self._current_run_id
                }
            )

        except Exception as e:
            # Save error to session if session_id provided
            if session_id:
                error_run_record = RunRecord(
                    run_id=self._current_run_id,
                    parent_run_id=None,
                    runner_type="team_leader",
                    runner_name=self.config.name,
                    task=message,
                    response=f"Error: {str(e)}",
                    success=False,
                    steps=0,
                    timestamp=time.time(),
                    metadata={"error": str(e)}
                )
                self.session_manager.add_run(session_id, error_run_record)

            return TeamRunResponse(
                success=False,
                team_name=self.config.name,
                message=f"Team execution failed: {str(e)}",
                member_runs=self.member_runs,
                total_steps=0,
                iterations=len(self.member_runs),
                metadata={"error": str(e), "run_id": self._current_run_id}
            )
