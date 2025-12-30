"""Base tool classes."""

from typing import Any
from pydantic import BaseModel


class ToolResult(BaseModel):
    """Tool execution result."""
    success: bool
    content: str | None = None
    error: str | None = None
    data: Any | None = None

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-serializable payload for LLM tool messages."""
        payload: dict[str, Any] = {"success": self.success}
        if self.content is not None:
            payload["content"] = self.content
        if self.data is not None:
            payload["data"] = self.data
        if self.error:
            payload["error"] = self.error
        return payload


def validate_tool_arguments(schema: dict[str, Any], arguments: Any) -> list[str]:
    """Validate tool arguments against a JSON Schema subset."""
    return _validate_schema(arguments, schema, path="$")


def _validate_schema(value: Any, schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []

    if "anyOf" in schema:
        if any(not _validate_schema(value, sub, path) for sub in schema["anyOf"]):
            return []
        return [f"{path}: value does not match anyOf schemas"]

    if "oneOf" in schema:
        matches = [not _validate_schema(value, sub, path) for sub in schema["oneOf"]]
        if sum(matches) == 1:
            return []
        return [f"{path}: value does not match exactly one schema in oneOf"]

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        if value is None and "null" in schema_type:
            return []
        non_null = [t for t in schema_type if t != "null"]
        if non_null:
            schema_type = non_null[0]

    if schema_type and not _matches_type(value, schema_type):
        return [f"{path}: expected {schema_type}, got {type(value).__name__}"]

    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: value must be one of {schema['enum']}"]

    if schema_type in {"integer", "number"} and isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append(f"{path}: value {value} is less than minimum {minimum}")
        if maximum is not None and value > maximum:
            errors.append(f"{path}: value {value} is greater than maximum {maximum}")

    if schema_type == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object"]
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: missing required field")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                errors.extend(_validate_schema(item, properties[key], path=f"{path}.{key}"))

    if schema_type == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array"]
        items_schema = schema.get("items")
        if items_schema:
            for idx, item in enumerate(value):
                errors.extend(_validate_schema(item, items_schema, path=f"{path}[{idx}]"))
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} items")
        if max_items is not None and len(value) > max_items:
            errors.append(f"{path}: expected at most {max_items} items")

    return errors


def _matches_type(value: Any, schema_type: str) -> bool:
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "null":
        return value is None
    return True


class Tool:
    """Base class for all tools."""

    @property
    def name(self) -> str:
        """Tool name."""
        raise NotImplementedError

    @property
    def description(self) -> str:
        """Tool description."""
        raise NotImplementedError

    @property
    def parameters(self) -> dict[str, Any]:
        """Tool parameters schema (JSON Schema format)."""
        raise NotImplementedError

    @property
    def instructions(self) -> str | None:
        """Tool usage instructions to be added to system prompt.

        返回 None 表示不添加说明到系统提示。
        返回字符串表示要添加的使用说明。

        Example:
            return '''
            When using this tool:
            - Always check the result carefully
            - Use absolute paths when possible
            '''
        """
        return None

    @property
    def add_instructions_to_prompt(self) -> bool:
        """是否将工具说明添加到系统提示."""
        return False

    async def execute(self, *args, **kwargs) -> ToolResult:
        """Execute the tool with arbitrary arguments."""
        raise NotImplementedError

    def to_schema(self) -> dict[str, Any]:
        """Convert tool to Anthropic tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }
