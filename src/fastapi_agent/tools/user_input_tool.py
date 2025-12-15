"""User input tool for human-in-the-loop interaction.

This tool allows the agent to pause execution and request additional
information from the user when needed.

Inspired by agno's UserControlFlowTools implementation.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field

from fastapi_agent.tools.base import Tool, ToolResult


class UserInputField(BaseModel):
    """Schema for a single user input field."""
    field_name: str = Field(..., description="The name of the field to get input for")
    field_type: str = Field(
        default="str",
        description="The type of the field (str, int, float, bool, list, dict)"
    )
    field_description: str = Field(..., description="A description of the field")
    value: Optional[Any] = Field(default=None, description="The value provided by user")


class UserInputRequest(BaseModel):
    """Request for user input with multiple fields."""
    fields: list[UserInputField] = Field(
        default_factory=list,
        description="List of fields requiring user input"
    )
    context: Optional[str] = Field(
        default=None,
        description="Additional context explaining why input is needed"
    )


class GetUserInputTool(Tool):
    """Tool for requesting user input during agent execution.
    
    When the agent needs additional information to proceed, it can call this
    tool to pause execution and request input from the user.
    
    The tool execution itself doesn't do anything - the agent loop detects
    this tool call and handles the pause/resume logic.
    """
    
    TOOL_NAME = "get_user_input"
    
    @property
    def name(self) -> str:
        return self.TOOL_NAME
    
    @property
    def description(self) -> str:
        return (
            "Request additional information from the user. Use this when you need "
            "clarification or missing information to complete a task. Provide all "
            "required fields as if the user were filling out a form."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_input_fields": {
                    "type": "array",
                    "description": "List of fields requiring user input",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field_name": {
                                "type": "string",
                                "description": "The name of the field"
                            },
                            "field_type": {
                                "type": "string",
                                "description": "The type of the field (str, int, float, bool, list, dict)",
                                "enum": ["str", "int", "float", "bool", "list", "dict"]
                            },
                            "field_description": {
                                "type": "string",
                                "description": "A description of what information is needed"
                            }
                        },
                        "required": ["field_name", "field_description"]
                    }
                },
                "context": {
                    "type": "string",
                    "description": "Additional context explaining why this input is needed"
                }
            },
            "required": ["user_input_fields"]
        }
    
    @property
    def instructions(self) -> str:
        return """
## User Input Tool Guidelines

You have access to the `get_user_input` tool to request information from the user.

### When to Use:
- When you don't have enough information to complete a task
- When you need clarification on ambiguous requirements
- When you need user confirmation or preferences
- When critical information is missing (e.g., API keys, file paths, configuration values)

### How to Use:
1. Call `get_user_input` with the fields you need
2. Provide clear, concise descriptions for each field
3. Specify the expected type for each field
4. Include context explaining why the information is needed

### Important Guidelines:
- **Don't guess or make up information** - ask the user instead
- **Include only required fields** - don't ask for information you already have
- **Provide clear descriptions** - help the user understand what's needed
- **Use appropriate field types** - this helps with input validation
- **Don't ask the same question twice** - accept whatever the user provides

### Example:
```json
{
    "user_input_fields": [
        {
            "field_name": "api_key",
            "field_type": "str",
            "field_description": "Your API key for the external service"
        },
        {
            "field_name": "output_format",
            "field_type": "str",
            "field_description": "Preferred output format (json, csv, or xml)"
        }
    ],
    "context": "I need these details to configure the data export"
}
```
"""
    
    @property
    def add_instructions_to_prompt(self) -> bool:
        return True
    
    async def execute(
        self,
        user_input_fields: list[dict[str, str]],
        context: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        """Execute the tool - actual logic is handled by agent loop.
        
        This method is called but the real handling happens in the agent's
        execution loop which detects this tool and pauses for user input.
        
        Args:
            user_input_fields: List of field definitions requiring input
            context: Optional context explaining why input is needed
            
        Returns:
            ToolResult indicating the request was registered
        """
        # The actual pause/resume logic is handled by the agent loop
        # This just returns a placeholder result
        return ToolResult(
            success=True,
            content="User input request registered. Waiting for user response."
        )


def is_user_input_tool_call(tool_name: str) -> bool:
    """Check if a tool call is for user input."""
    return tool_name == GetUserInputTool.TOOL_NAME


def parse_user_input_fields(arguments: dict[str, Any]) -> list[UserInputField]:
    """Parse user input fields from tool call arguments.
    
    Args:
        arguments: Tool call arguments containing user_input_fields
        
    Returns:
        List of UserInputField objects
    """
    fields = []
    for field_data in arguments.get("user_input_fields", []):
        fields.append(UserInputField(
            field_name=field_data.get("field_name", ""),
            field_type=field_data.get("field_type", "str"),
            field_description=field_data.get("field_description", ""),
        ))
    return fields
