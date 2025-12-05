"""Team orchestration for multi-agent collaboration."""

import asyncio
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.session import RunRecord, TeamSession
from fastapi_agent.core.session_manager import UnifiedTeamSessionManager
from fastapi_agent.core.trace_logger import TraceLogger, get_current_trace, set_current_trace
from fastapi_agent.schemas.team import (
    TeamConfig,
    TeamMemberConfig,
    MemberRunResult,
    TeamRunResponse,
    TaskWithDependencies,
    DependencyRunResponse,
)
from fastapi_agent.tools.base import Tool, ToolResult
from fastapi_agent.tools.spawn_agent_tool import SpawnAgentTool


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

    async def execute(self, member_name: str, task: str) -> ToolResult:
        """Execute task delegation."""
        member_config = None
        for m in self.team.config.members:
            if m.name == member_name:
                member_config = m
                break

        if not member_config:
            return ToolResult(success=False, error=f"Member '{member_name}' not found in team")

        trace = get_current_trace()
        if trace:
            trace.log_delegation("Leader", member_name, task)

        result = await self.team._run_member(member_config, task, session_id=self.session_id)

        if result.success:
            return ToolResult(success=True, content=f"{member_name} completed task:\n{result.response}")
        else:
            return ToolResult(success=False, content=result.response, error=result.error)


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

    async def execute(self, task: str) -> ToolResult:
        """Execute task delegation to all members."""
        results = []
        all_success = True
        for member_config in self.team.config.members:
            result = await self.team._run_member(member_config, task, session_id=self.session_id)
            if result.success:
                results.append(f"[{member_config.name}]: {result.response}")
            else:
                results.append(f"[{member_config.name}] FAILED: {result.error}")
                all_success = False

        return ToolResult(success=all_success, content="\n\n".join(results))


class Team:
    """Team of agents that can collaborate on tasks."""

    def __init__(
        self,
        config: TeamConfig,
        llm_client: LLMClient,
        available_tools: Optional[List[Tool]] = None,
        workspace_dir: str = "./workspace",
        session_manager: Optional[UnifiedTeamSessionManager] = None,
        enable_spawn_agent: bool = True,
        spawn_agent_max_depth: int = 3,
        spawn_agent_default_max_steps: int = 15,
        spawn_agent_token_limit: int = 50000,
        current_depth: int = 0,  # Depth tracking for nested Team/SpawnAgent
    ):
        self.config = config
        self.llm_client = llm_client
        self.available_tools = available_tools or []
        self.workspace_dir = workspace_dir
        self.team_id = str(uuid4())
        self.session_manager = session_manager or UnifiedTeamSessionManager()

        # Spawn Agent configuration
        self.enable_spawn_agent = enable_spawn_agent
        self.spawn_agent_max_depth = spawn_agent_max_depth
        self.spawn_agent_default_max_steps = spawn_agent_default_max_steps
        self.spawn_agent_token_limit = spawn_agent_token_limit
        self.current_depth = current_depth  # Team execution counts as depth

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

    async def _run_member(
        self,
        member_config: TeamMemberConfig,
        task: str,
        session_id: Optional[str] = None,
        depth: int = 1
    ) -> MemberRunResult:
        """Run a specific team member on a task."""
        trace = get_current_trace()
        if trace:
            trace.log_agent_start(
                member_config.name,
                member_config.role,
                task,
                parent_agent="Leader",
                depth=depth
            )

        try:
            member_tools = []
            if member_config.tools:
                for tool in self.available_tools:
                    if tool.name in member_config.tools:
                        member_tools.append(tool)

                # Add SpawnAgentTool if member has it in their tools and it's enabled
                if (self.enable_spawn_agent and
                    "spawn_agent" in member_config.tools and
                    self.current_depth < self.spawn_agent_max_depth):

                    # Create parent tools dict for spawn agent (member's other tools)
                    parent_tools = {t.name: t for t in member_tools}

                    spawn_tool = SpawnAgentTool(
                        llm_client=self.llm_client,
                        parent_tools=parent_tools,
                        workspace_dir=self.workspace_dir,
                        current_depth=self.current_depth + 1,  # Team member is depth + 1
                        max_depth=self.spawn_agent_max_depth,
                        default_max_steps=self.spawn_agent_default_max_steps,
                        default_token_limit=self.spawn_agent_token_limit,
                    )
                    member_tools.append(spawn_tool)

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

            member_agent.add_user_message(task)
            response_content, logs = await member_agent.run()

            steps = len([log for log in logs if log.get("type") == "step"])
            max_steps_reached = any(log.get("type") == "max_steps_reached" for log in logs)
            llm_failed = response_content and response_content.startswith("LLM call failed")
            success = bool(response_content) and not max_steps_reached and not llm_failed

            input_tokens = 0
            output_tokens = 0
            for log in logs:
                if log.get("type") in ("completion", "max_steps_reached"):
                    input_tokens = log.get("total_input_tokens", 0)
                    output_tokens = log.get("total_output_tokens", 0)
                    break

            result = MemberRunResult(
                member_name=member_config.name,
                member_role=member_config.role,
                task=task,
                response=response_content,
                success=success,
                steps=steps,
                metadata={"input_tokens": input_tokens, "output_tokens": output_tokens}
            )

            if trace:
                trace.log_agent_end(member_config.name, success, response_content, steps, input_tokens, output_tokens)

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
                    metadata={"role": member_config.role, "logs": logs}
                )
                await self.session_manager.add_run(session_id, member_run_record)

            return result

        except Exception as e:
            if trace:
                trace.log_agent_end(member_config.name, False, str(e), 0)

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
                await self.session_manager.add_run(session_id, member_run_record)

            return result

    async def run(
        self,
        message: str,
        max_steps: int = 50,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        num_history_runs: int = 3
    ) -> TeamRunResponse:
        """Run the team on a task."""
        self.member_runs = []
        self.iteration_count = 0
        self._current_run_id = str(uuid4())

        trace = TraceLogger()
        trace.start_trace("team", {
            "team_name": self.config.name,
            "members": [m.name for m in self.config.members]
        })
        set_current_trace(trace)

        try:
            trace.log_agent_start("Leader", "Team Leader", message, depth=0)

            history_context = ""
            if session_id:
                session = await self.session_manager.get_session(
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

            # Add task message and run the leader
            leader.add_user_message(message)
            response_content, logs = await leader.run()

            leader_steps = len([log for log in logs if log.get("type") == "step"])
            total_steps = leader_steps
            for member_run in self.member_runs:
                total_steps += member_run.steps

            leader_input_tokens = 0
            leader_output_tokens = 0
            for log in logs:
                if log.get("type") in ("completion", "max_steps_reached"):
                    leader_input_tokens = log.get("total_input_tokens", 0)
                    leader_output_tokens = log.get("total_output_tokens", 0)
                    break

            max_steps_reached = any(log.get("type") == "max_steps_reached" for log in logs)
            llm_failed = response_content and response_content.startswith("LLM call failed")
            success = bool(response_content) and not max_steps_reached and not llm_failed

            if session_id:
                leader_run_record = RunRecord(
                    run_id=self._current_run_id,
                    parent_run_id=None,  # Leader has no parent
                    runner_type="team_leader",
                    runner_name=self.config.name,
                    task=message,
                    response=response_content,
                    success=success,
                    steps=total_steps,
                    timestamp=time.time(),
                    metadata={
                        "logs": logs,
                        "member_count": len(self.member_runs)
                    }
                )
                await self.session_manager.add_run(session_id, leader_run_record)

            trace.log_agent_end("Leader", success, response_content, leader_steps, leader_input_tokens, leader_output_tokens)
            trace.end_trace(success=success, result=response_content)
            set_current_trace(None)

            return TeamRunResponse(
                success=success,
                team_name=self.config.name,
                message=response_content,
                member_runs=self.member_runs,
                total_steps=total_steps,
                iterations=len(self.member_runs),
                metadata={
                    "session_id": session_id,
                    "run_id": self._current_run_id,
                    "trace_id": trace.trace_id,
                    "input_tokens": leader_input_tokens,
                    "output_tokens": leader_output_tokens,
                }
            )

        except Exception as e:
            trace.log_agent_end("Leader", False, str(e), 0)
            trace.end_trace(success=False, result=str(e))
            set_current_trace(None)

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
                await self.session_manager.add_run(session_id, error_run_record)

            return TeamRunResponse(
                success=False,
                team_name=self.config.name,
                message=f"Team execution failed: {str(e)}",
                member_runs=self.member_runs,
                total_steps=0,
                iterations=len(self.member_runs),
                metadata={"error": str(e), "run_id": self._current_run_id, "trace_id": trace.trace_id}
            )

    def _resolve_dependencies(
        self, tasks: List[TaskWithDependencies]
    ) -> List[List[TaskWithDependencies]]:
        """Resolve task dependencies using topological sort.

        Args:
            tasks: List of tasks with dependencies

        Returns:
            List of task layers (each layer can be executed in parallel)

        Raises:
            ValueError: If circular dependencies detected
        """
        task_map = {task.id: task for task in tasks}
        in_degree = {task.id: len(task.depends_on) for task in tasks}

        for task in tasks:
            for dep_id in task.depends_on:
                if dep_id not in task_map:
                    raise ValueError(f"Task '{task.id}' depends on non-existent task '{dep_id}'")

        layers = []
        remaining = set(task.id for task in tasks)

        while remaining:
            current_layer = [
                task_map[task_id]
                for task_id in remaining
                if in_degree[task_id] == 0
            ]

            if not current_layer:
                raise ValueError(f"Circular dependency detected among tasks: {remaining}")

            layers.append(current_layer)

            for task in current_layer:
                remaining.remove(task.id)
                for other_id in remaining:
                    if task.id in task_map[other_id].depends_on:
                        in_degree[other_id] -= 1

        return layers

    async def _execute_task_with_context(
        self,
        task: TaskWithDependencies,
        completed_results: Dict[str, str],
        session_id: Optional[str] = None,
        layer: int = 0,
    ) -> TaskWithDependencies:
        """Execute a single task with context from completed dependencies."""
        task.status = "running"
        start_time = time.time()

        try:
            member_config = None
            for m in self.config.members:
                if m.role == task.assigned_to:
                    member_config = m
                    break

            if not member_config:
                task.status = "failed"
                task.result = f"Error: No member with role '{task.assigned_to}' found"
                return task

            task_description = task.task
            if task.depends_on:
                context_parts = ["\n\n依赖任务结果:"]
                for dep_id in task.depends_on:
                    if dep_id in completed_results:
                        context_parts.append(f"\n[{dep_id}]: {completed_results[dep_id]}")
                task_description += "".join(context_parts)

            member_result = await self._run_member(
                member_config, task_description, session_id=session_id
            )

            if member_result.success:
                task.status = "completed"
                task.result = member_result.response
            else:
                task.status = "failed"
                task.result = member_result.error or "Unknown error"

            elapsed = time.time() - start_time
            task.metadata = {
                "member_name": member_result.member_name,
                "steps": member_result.steps,
                "logs": member_result.metadata.get("logs", []),
                "elapsed": elapsed,
            }

            trace = get_current_trace()
            if trace:
                trace.log_task_end(task.id, task.status, task.result, elapsed)

            return task

        except Exception as e:
            elapsed = time.time() - start_time
            task.status = "failed"
            task.result = f"Execution error: {str(e)}"

            trace = get_current_trace()
            if trace:
                trace.log_task_end(task.id, "failed", str(e), elapsed)

            return task

    async def run_with_dependencies(
        self,
        tasks: List[TaskWithDependencies],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> DependencyRunResponse:
        """Execute tasks with dependency relationships."""
        self._current_run_id = str(uuid4())

        trace = TraceLogger()
        trace.start_trace("dependency_workflow", {
            "team_name": self.config.name,
            "task_count": len(tasks),
            "task_ids": [t.id for t in tasks]
        })
        set_current_trace(trace)

        try:
            layers = self._resolve_dependencies(tasks)
            execution_order = [[task.id for task in layer] for layer in layers]

            completed_results = {}
            total_steps = 0

            for layer_idx, layer in enumerate(layers):
                for task in layer:
                    trace.log_task_start(
                        task.id, task.task, task.assigned_to, task.depends_on, layer_idx
                    )

                layer_results = await asyncio.gather(*[
                    self._execute_task_with_context(task, completed_results, session_id, layer_idx)
                    for task in layer
                ])

                for task in layer_results:
                    completed_results[task.id] = task.result or ""
                    total_steps += task.metadata.get("steps", 0)

                    if task.status == "failed":
                        remaining_tasks = []
                        for remaining_layer in layers[layer_idx + 1:]:
                            remaining_tasks.extend(remaining_layer)

                        for remaining_task in remaining_tasks:
                            remaining_task.status = "skipped"
                            remaining_task.result = f"Skipped due to dependency failure: {task.id}"

                        final_message = f"执行失败：任务 '{task.id}' 执行失败\n\n失败详情:\n{task.result}"

                        trace.end_trace(success=False, result=final_message)
                        set_current_trace(None)

                        if session_id:
                            await self._save_dependency_run_to_session(
                                session_id=session_id,
                                tasks=tasks,
                                final_message=final_message,
                                success=False,
                                total_steps=total_steps,
                            )

                        return DependencyRunResponse(
                            success=False,
                            team_name=self.config.name,
                            message=final_message,
                            tasks=tasks,
                            execution_order=execution_order,
                            total_steps=total_steps,
                            metadata={"run_id": self._current_run_id, "failed_task": task.id, "trace_id": trace.trace_id},
                        )

            completed_tasks = [t for t in tasks if t.status == "completed"]
            final_message = f"所有任务执行完成 ({len(completed_tasks)}/{len(tasks)})\n\n执行结果:\n"
            for task in tasks:
                final_message += f"\n[{task.id}] {task.status}: {task.result[:200]}..."

            trace.end_trace(success=True, result=final_message)
            set_current_trace(None)

            if session_id:
                await self._save_dependency_run_to_session(
                    session_id=session_id,
                    tasks=tasks,
                    final_message=final_message,
                    success=True,
                    total_steps=total_steps,
                )

            return DependencyRunResponse(
                success=True,
                team_name=self.config.name,
                message=final_message,
                tasks=tasks,
                execution_order=execution_order,
                total_steps=total_steps,
                metadata={"run_id": self._current_run_id, "trace_id": trace.trace_id},
            )

        except Exception as e:
            error_message = f"依赖执行失败: {str(e)}"

            trace.end_trace(success=False, result=error_message)
            set_current_trace(None)

            if session_id:
                await self._save_dependency_run_to_session(
                    session_id=session_id,
                    tasks=tasks,
                    final_message=error_message,
                    success=False,
                    total_steps=0,
                )

            return DependencyRunResponse(
                success=False,
                team_name=self.config.name,
                message=error_message,
                tasks=tasks,
                execution_order=[],
                total_steps=0,
                metadata={"error": str(e), "run_id": self._current_run_id, "trace_id": trace.trace_id},
            )

    async def _save_dependency_run_to_session(
        self,
        session_id: str,
        tasks: List[TaskWithDependencies],
        final_message: str,
        success: bool,
        total_steps: int,
    ) -> None:
        """Save dependency run results to session."""
        run_record = RunRecord(
            run_id=self._current_run_id,
            parent_run_id=None,
            runner_type="team_dependency",
            runner_name=self.config.name,
            task=f"Dependency-based execution with {len(tasks)} tasks",
            response=final_message,
            success=success,
            steps=total_steps,
            timestamp=time.time(),
            metadata={
                "tasks": [task.model_dump() for task in tasks],
                "task_count": len(tasks),
            },
        )
        await self.session_manager.add_run(session_id, run_record)
