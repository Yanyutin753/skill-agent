"""Vision Agent Tool - A sub-agent with vision model and desktop control capabilities."""

from typing import Any, Optional

from fastapi_agent.tools.base import Tool, ToolResult


class VisionAgentTool(Tool):
    """Spawn a vision-capable sub-agent for desktop visual tasks.

    This tool creates a sub-agent that uses a vision model (e.g., qwen-vl-max)
    and has access to desktop control tools (screenshot, click, type, etc.).

    The vision agent can:
    - Take screenshots and understand what's on screen
    - Find and click on UI elements
    - Read text from the screen
    - Perform complex visual automation tasks

    Use this tool when you need to:
    - See what's currently displayed on screen
    - Interact with GUI applications
    - Find specific UI elements or text
    - Perform visual verification
    """

    @property
    def name(self) -> str:
        return "vision_agent"

    @property
    def description(self) -> str:
        return (
            "调用视觉 Agent 执行桌面视觉任务。视觉 Agent 可以截图、理解屏幕内容、"
            "点击按钮、输入文字等。适用于需要'看'屏幕的任务。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "要执行的视觉任务描述。例如：'截图并描述屏幕内容'、"
                        "'找到并点击确定按钮'、'打开微信应用'"
                    ),
                },
                "max_steps": {
                    "type": "integer",
                    "description": "视觉 Agent 最大执行步数，默认 10",
                    "default": 10,
                },
            },
            "required": ["task"],
        }

    async def execute(
        self,
        task: str,
        max_steps: int = 10,
    ) -> ToolResult:
        """Execute a visual task using the vision agent."""
        try:
            from fastapi_agent.core.config import settings
            from fastapi_agent.core.llm_client import LLMClient
            from fastapi_agent.core.agent import Agent
            from fastapi_agent.tools.desktop_tool import (
                DesktopScreenshotTool,
                DesktopClickTool,
                DesktopTypeTool,
                DesktopHotkeyTool,
                DesktopFindTool,
                DesktopScrollTool,
                DesktopPressKeyTool,
            )

            # Get vision model config
            vision_model = settings.VISION_MODEL
            if not vision_model:
                return ToolResult(
                    success=False,
                    error="VISION_MODEL not configured. Please set VISION_MODEL in .env (e.g., dashscope/qwen-vl-max)",
                )

            api_key = settings.VISION_API_KEY or settings.LLM_API_KEY
            api_base = settings.VISION_API_BASE or settings.LLM_API_BASE or None

            # Create vision LLM client
            vision_llm = LLMClient(
                api_key=api_key,
                api_base=api_base,
                model=vision_model,
            )

            # Desktop control tools for vision agent
            desktop_tools = [
                DesktopScreenshotTool(),
                DesktopClickTool(),
                DesktopTypeTool(),
                DesktopHotkeyTool(),
                DesktopFindTool(),
                DesktopScrollTool(),
                DesktopPressKeyTool(),
            ]

            # Vision agent system prompt
            vision_system_prompt = """你是一个视觉 Agent，专门负责桌面视觉任务。

## 你的能力
- 截取屏幕截图并理解内容（你是视觉模型，可以直接看到截图）
- 点击屏幕上的元素（通过坐标或文字定位）
- 输入文字
- 执行键盘快捷键
- 查找屏幕上的文字或元素

## 工作方式
1. 首先使用 desktop_screenshot 截图查看当前屏幕状态
2. 根据截图内容决定下一步操作
3. 执行必要的点击、输入等操作
4. 如果需要验证操作结果，再次截图确认

## 注意事项
- 每次操作后建议截图确认结果
- 如果找不到目标元素，尝试滚动或等待
- 返回清晰的执行结果描述
"""

            # Create vision agent
            vision_agent = Agent(
                llm_client=vision_llm,
                system_prompt=vision_system_prompt,
                tools=desktop_tools,
                max_steps=max_steps,
                enable_logging=False,  # Don't create separate log for sub-agent
            )

            # Execute task
            vision_agent.add_user_message(task)
            result, logs = await vision_agent.run()

            # Summarize execution
            steps_taken = len([log for log in logs if log.get("type") == "step"])

            return ToolResult(
                success=True,
                content=f"**视觉 Agent 执行结果** (步数: {steps_taken})\n\n{result}",
            )

        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"Desktop control not available: {e}. Install with: uv sync --extra desktop",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Vision agent execution failed: {str(e)}",
            )
