"""Desktop control tools for system-level UI automation.

These tools enable the agent to control any application on the desktop,
including mouse movement, keyboard input, screen capture, and UI element detection.
"""

from typing import Any, List, Optional

from fastapi_agent.tools.base import Tool, ToolResult


class DesktopScreenshotTool(Tool):
    """Take a screenshot of the current screen for visual analysis.

    The screenshot is returned as a base64 encoded image that can be
    analyzed by the LLM to understand what's displayed on screen.
    """

    @property
    def name(self) -> str:
        return "desktop_screenshot"

    @property
    def description(self) -> str:
        return (
            "Take a screenshot of the current screen. The image will be analyzed "
            "to understand what's visible on the desktop. Use this to see the current "
            "state of applications, verify actions, or find UI elements."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "active_app_only": {
                    "type": "boolean",
                    "description": "If true, capture only the active application window instead of full screen",
                    "default": False,
                },
            },
            "required": [],
        }

    async def execute(self, active_app_only: bool = False) -> ToolResult:
        """Execute screenshot capture."""
        try:
            from fastapi_agent.services.desktop_controller import get_desktop_controller

            controller = get_desktop_controller()
            image_base64 = await controller.screenshot(active_app_only=active_app_only)

            return ToolResult(
                success=True,
                content="Screenshot captured successfully. The image is being analyzed.",
                image_base64=image_base64,
            )
        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"Desktop control not available: {e}. Install with: uv sync --extra desktop",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Screenshot failed: {str(e)}")


class DesktopClickTool(Tool):
    """Click at a screen position or on text found via OCR."""

    @property
    def name(self) -> str:
        return "desktop_click"

    @property
    def description(self) -> str:
        return (
            "Click on the screen at specified coordinates or on text found via OCR. "
            "Use coordinates (x, y) for precise clicking, or use 'text' to click on "
            "visible text on the screen (the text will be found using OCR)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {
                    "type": "integer",
                    "description": "X coordinate to click (used if text is not provided)",
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate to click (used if text is not provided)",
                },
                "text": {
                    "type": "string",
                    "description": "Text to find and click on (uses OCR to locate)",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button to use",
                    "default": "left",
                },
                "double_click": {
                    "type": "boolean",
                    "description": "Whether to double-click",
                    "default": False,
                },
            },
            "required": [],
        }

    async def execute(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        text: Optional[str] = None,
        button: str = "left",
        double_click: bool = False,
    ) -> ToolResult:
        """Execute mouse click."""
        try:
            from fastapi_agent.services.desktop_controller import get_desktop_controller

            controller = get_desktop_controller()
            clicks = 2 if double_click else 1

            await controller.click(x=x, y=y, text=text, button=button, clicks=clicks)

            location = f"text '{text}'" if text else f"coordinates ({x}, {y})"
            click_type = "Double-clicked" if double_click else "Clicked"

            return ToolResult(
                success=True,
                content=f"{click_type} at {location} with {button} button",
            )
        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"Desktop control not available: {e}",
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Click failed: {str(e)}")


class DesktopTypeTool(Tool):
    """Type text at the current cursor position."""

    @property
    def name(self) -> str:
        return "desktop_type"

    @property
    def description(self) -> str:
        return (
            "Type text at the current cursor/focus position. The text will be typed "
            "as if entered on a physical keyboard. Use this to fill in forms, write "
            "in text editors, enter search queries, etc."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to type",
                },
            },
            "required": ["text"],
        }

    async def execute(self, text: str) -> ToolResult:
        """Execute text typing."""
        try:
            from fastapi_agent.services.desktop_controller import get_desktop_controller

            controller = get_desktop_controller()
            await controller.type_text(text)

            # Truncate display if text is long
            display_text = text[:50] + "..." if len(text) > 50 else text

            return ToolResult(
                success=True,
                content=f"Typed: {display_text}",
            )
        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"Desktop control not available: {e}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Type failed: {str(e)}")


class DesktopHotkeyTool(Tool):
    """Execute keyboard shortcuts and hotkey combinations."""

    @property
    def name(self) -> str:
        return "desktop_hotkey"

    @property
    def description(self) -> str:
        return (
            "Execute keyboard shortcuts like Cmd+C (copy), Cmd+V (paste), "
            "Cmd+Space (Spotlight on macOS), Ctrl+S (save), etc. "
            "Keys should be provided as a list. Common modifier keys: "
            "'command' or 'cmd' (macOS), 'ctrl' or 'control', 'alt' or 'option', 'shift'."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of keys to press together. Examples: "
                        "['command', 'c'] for copy, ['command', 'space'] for Spotlight, "
                        "['ctrl', 'shift', 'n'] for new window"
                    ),
                },
            },
            "required": ["keys"],
        }

    async def execute(self, keys: List[str]) -> ToolResult:
        """Execute hotkey combination."""
        try:
            from fastapi_agent.services.desktop_controller import get_desktop_controller

            controller = get_desktop_controller()
            await controller.hotkey(*keys)

            return ToolResult(
                success=True,
                content=f"Executed hotkey: {'+'.join(keys)}",
            )
        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"Desktop control not available: {e}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Hotkey failed: {str(e)}")


class DesktopFindTool(Tool):
    """Find text or UI elements on the screen."""

    @property
    def name(self) -> str:
        return "desktop_find"

    @property
    def description(self) -> str:
        return (
            "Find text or UI elements on the screen and return their coordinates. "
            "Use 'text' to search for visible text via OCR, or use 'element_description' "
            "to search for UI elements like buttons, icons, etc. using visual recognition."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to find on screen (uses OCR)",
                },
                "element_description": {
                    "type": "string",
                    "description": "Description of UI element to find (e.g., 'close button', 'search icon')",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        text: Optional[str] = None,
        element_description: Optional[str] = None,
    ) -> ToolResult:
        """Execute element finding."""
        try:
            from fastapi_agent.services.desktop_controller import get_desktop_controller

            controller = get_desktop_controller()

            if text:
                result = await controller.find_text(text)
                target = f"text '{text}'"
            elif element_description:
                result = await controller.find_element(element_description)
                target = f"element '{element_description}'"
            else:
                return ToolResult(
                    success=False,
                    error="Either 'text' or 'element_description' must be provided",
                )

            if result:
                x, y = result
                return ToolResult(
                    success=True,
                    content=f"Found {target} at coordinates ({x}, {y})",
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"Could not find {target} on screen",
                )
        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"Desktop control not available: {e}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Find failed: {str(e)}")


class DesktopScrollTool(Tool):
    """Scroll the mouse wheel up or down."""

    @property
    def name(self) -> str:
        return "desktop_scroll"

    @property
    def description(self) -> str:
        return (
            "Scroll the mouse wheel up or down. Use positive values to scroll up, "
            "negative values to scroll down. The amount corresponds to scroll 'clicks'."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "integer",
                    "description": "Amount to scroll (positive=up, negative=down)",
                },
            },
            "required": ["amount"],
        }

    async def execute(self, amount: int) -> ToolResult:
        """Execute mouse scroll."""
        try:
            from fastapi_agent.services.desktop_controller import get_desktop_controller

            controller = get_desktop_controller()
            await controller.scroll(amount)

            direction = "up" if amount > 0 else "down"
            return ToolResult(
                success=True,
                content=f"Scrolled {direction} by {abs(amount)} clicks",
            )
        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"Desktop control not available: {e}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Scroll failed: {str(e)}")


class DesktopPressKeyTool(Tool):
    """Press a single keyboard key."""

    @property
    def name(self) -> str:
        return "desktop_press_key"

    @property
    def description(self) -> str:
        return (
            "Press a single keyboard key. Use this for special keys like 'return', "
            "'escape', 'tab', 'space', 'backspace', 'delete', arrow keys ('up', 'down', "
            "'left', 'right'), function keys ('f1'-'f12'), etc."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key to press (e.g., 'return', 'escape', 'tab', 'up', 'down')",
                },
                "times": {
                    "type": "integer",
                    "description": "Number of times to press the key",
                    "default": 1,
                },
            },
            "required": ["key"],
        }

    async def execute(self, key: str, times: int = 1) -> ToolResult:
        """Execute key press."""
        try:
            from fastapi_agent.services.desktop_controller import get_desktop_controller

            controller = get_desktop_controller()
            await controller.press_key(key, presses=times)

            times_str = f" {times} times" if times > 1 else ""
            return ToolResult(
                success=True,
                content=f"Pressed '{key}'{times_str}",
            )
        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"Desktop control not available: {e}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Key press failed: {str(e)}")


# Export all desktop tools
__all__ = [
    "DesktopScreenshotTool",
    "DesktopClickTool",
    "DesktopTypeTool",
    "DesktopHotkeyTool",
    "DesktopFindTool",
    "DesktopScrollTool",
    "DesktopPressKeyTool",
]
