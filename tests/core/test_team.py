"""Tests for Team functionality."""

import pytest
from unittest.mock import Mock, patch

from fastapi_agent.core.team import Team, DelegateTaskTool, DelegateToAllTool
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.schemas.team import TeamConfig, TeamMemberConfig
from fastapi_agent.tools.base_tools import ReadTool, WriteTool


@pytest.fixture
def llm_client():
    """Create a mock LLM client."""
    client = Mock(spec=LLMClient)
    return client


@pytest.fixture
def sample_team_config():
    """Create a sample team configuration."""
    return TeamConfig(
        name="Research Team",
        description="A team for research tasks",
        members=[
            TeamMemberConfig(
                name="Researcher",
                role="Information gathering specialist",
                instructions="Find and summarize information",
                tools=[]
            ),
            TeamMemberConfig(
                name="Writer",
                role="Documentation specialist",
                instructions="Create clear documentation",
                tools=["write_file"]
            )
        ],
        model="openai:gpt-4o-mini"
    )


@pytest.fixture
def available_tools():
    """Create list of available tools."""
    return [
        ReadTool(),
        WriteTool()
    ]


def test_team_initialization(llm_client, sample_team_config, available_tools):
    """Test team initialization."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    assert team.config.name == "Research Team"
    assert len(team.config.members) == 2
    assert team.team_id is not None
    assert team.member_runs == []
    assert team.iteration_count == 0


def test_delegate_task_tool_initialization(llm_client, sample_team_config, available_tools):
    """Test DelegateTaskTool initialization."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tool = DelegateTaskTool(team)

    assert tool.name == "delegate_task_to_member"
    assert "Delegate a task" in tool.description

    params = tool.parameters
    assert params["type"] == "object"
    assert "member_name" in params["properties"]
    assert "task" in params["properties"]

    # Check member enum
    member_enum = params["properties"]["member_name"]["enum"]
    assert "Researcher" in member_enum
    assert "Writer" in member_enum


def test_delegate_to_all_tool_initialization(llm_client, sample_team_config, available_tools):
    """Test DelegateToAllTool initialization."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tool = DelegateToAllTool(team)

    assert tool.name == "delegate_task_to_all_members"
    assert "ALL team members" in tool.description

    params = tool.parameters
    assert "task" in params["properties"]
    assert params["required"] == ["task"]


def test_get_leader_tools_single_delegation(llm_client, sample_team_config, available_tools):
    """Test getting leader tools for single member delegation."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tools = team._get_leader_tools()

    assert len(tools) == 1
    assert isinstance(tools[0], DelegateTaskTool)


def test_get_leader_tools_all_delegation(llm_client, available_tools):
    """Test getting leader tools for all-member delegation."""
    config = TeamConfig(
        name="Brainstorm Team",
        members=[
            TeamMemberConfig(name="Member1", role="Role1"),
            TeamMemberConfig(name="Member2", role="Role2")
        ],
        delegate_to_all=True
    )

    team = Team(
        config=config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tools = team._get_leader_tools()

    assert len(tools) == 1
    assert isinstance(tools[0], DelegateToAllTool)


def test_build_leader_system_prompt(llm_client, sample_team_config, available_tools):
    """Test building leader system prompt."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    prompt = team._build_leader_system_prompt()

    # Check key sections
    assert "Research Team" in prompt
    assert "Researcher" in prompt
    assert "Writer" in prompt
    assert "delegate_task_to_member" in prompt
    assert "Information gathering specialist" in prompt
    assert "Documentation specialist" in prompt


def test_build_leader_system_prompt_delegate_all(llm_client, available_tools):
    """Test building leader system prompt for delegate-to-all mode."""
    config = TeamConfig(
        name="Creative Team",
        description="Creative brainstorming",
        members=[
            TeamMemberConfig(name="Member1", role="Creative"),
            TeamMemberConfig(name="Member2", role="Analytical")
        ],
        delegate_to_all=True,
        leader_instructions="Focus on innovative solutions"
    )

    team = Team(
        config=config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    prompt = team._build_leader_system_prompt()

    assert "delegate_task_to_all_members" in prompt
    assert "ALL team members" in prompt.lower()
    assert "Focus on innovative solutions" in prompt


def test_run_member_success(llm_client, sample_team_config, available_tools):
    """Test running a team member successfully."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    # Mock agent run
    mock_response = {
        "success": True,
        "message": "Research completed",
        "steps": 3
    }

    with patch("fastapi_agent.core.team.Agent") as MockAgent:
        mock_agent_instance = Mock()
        mock_agent_instance.run.return_value = mock_response
        MockAgent.return_value = mock_agent_instance

        member_config = sample_team_config.members[0]
        result = team._run_member(member_config, "Find information about Python")

        assert result.success is True
        assert result.member_name == "Researcher"
        assert result.response == "Research completed"
        assert result.steps == 3
        assert len(team.member_runs) == 1


def test_run_member_with_tools(llm_client, sample_team_config, available_tools):
    """Test running a team member with specific tools."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    mock_response = {
        "success": True,
        "message": "File written",
        "steps": 2
    }

    with patch("fastapi_agent.core.team.Agent") as MockAgent:
        mock_agent_instance = Mock()
        mock_agent_instance.run.return_value = mock_response
        MockAgent.return_value = mock_agent_instance

        # Writer has write_file tool
        member_config = sample_team_config.members[1]
        result = team._run_member(member_config, "Write documentation")

        # Check that agent was created with write_file tool
        call_args = MockAgent.call_args
        agent_tools = call_args[1]["tools"]

        assert result.success is True
        assert result.member_name == "Writer"


def test_run_member_error(llm_client, sample_team_config, available_tools):
    """Test handling member run error."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    with patch("fastapi_agent.core.team.Agent") as MockAgent:
        MockAgent.side_effect = Exception("Agent failed")

        member_config = sample_team_config.members[0]
        result = team._run_member(member_config, "Some task")

        assert result.success is False
        assert result.error == "Agent failed"
        assert len(team.member_runs) == 1


def test_delegate_task_tool_member_not_found(llm_client, sample_team_config, available_tools):
    """Test delegating to non-existent member."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    tool = DelegateTaskTool(team)
    result = tool.execute(member_name="NonExistent", task="Some task")

    assert "not found" in result
    assert "NonExistent" in result


def test_team_run_integration(llm_client, sample_team_config, available_tools):
    """Test full team run integration."""
    team = Team(
        config=sample_team_config,
        llm_client=llm_client,
        available_tools=available_tools
    )

    # Mock leader agent run
    mock_leader_response = {
        "success": True,
        "message": "Task completed by delegating to team members",
        "steps": 5
    }

    with patch("fastapi_agent.core.team.Agent") as MockAgent:
        mock_agent_instance = Mock()
        mock_agent_instance.run.return_value = mock_leader_response
        MockAgent.return_value = mock_agent_instance

        response = team.run("Research Python and create documentation")

        assert response.success is True
        assert response.team_name == "Research Team"
        assert response.message == "Task completed by delegating to team members"
        assert "leader_response" in response.metadata
        assert "team_config" in response.metadata
