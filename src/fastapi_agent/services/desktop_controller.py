"""Desktop control service using Open Interpreter."""

import base64
from io import BytesIO
from typing import Optional, Tuple


class DesktopController:
    """Desktop control service wrapping Open Interpreter's computer API.

    Provides system-level desktop control capabilities including:
    - Mouse control (move, click, drag, scroll)
    - Keyboard input (type text, hotkeys, key press)
    - Screen capture (screenshot)
    - UI element detection (find text, find element by description)
    - OCR (optical character recognition)

    This service can control ANY application on the desktop, not just browsers.
    """

    def __init__(self):
        """Initialize desktop controller."""
        self._computer = None
        self._pyautogui = None

    def _get_pyautogui(self):
        """Get pyautogui module with lazy loading."""
        if self._pyautogui is None:
            try:
                import pyautogui
                # Disable fail-safe for automation
                pyautogui.FAILSAFE = False
                self._pyautogui = pyautogui
            except ImportError:
                raise ImportError(
                    "Desktop control requires pyautogui. "
                    "Install with: uv add pyautogui"
                )
        return self._pyautogui

    def _init_computer(self):
        """Lazy initialize the computer API."""
        if self._computer is None:
            try:
                from interpreter import computer
                self._computer = computer
            except ImportError:
                raise ImportError(
                    "Desktop control requires open-interpreter. "
                    "Install with: uv add open-interpreter or uv sync --extra desktop"
                )

    @property
    def computer(self):
        """Get the computer API instance."""
        if self._computer is None:
            self._init_computer()
        return self._computer

    async def screenshot(
        self,
        full_screen: bool = True,
        active_app_only: bool = False,
    ) -> str:
        """Take a screenshot of the screen.

        Args:
            full_screen: Whether to capture the full screen
            active_app_only: Whether to capture only the active application window

        Returns:
            Base64 encoded PNG image string
        """
        # Use pyautogui directly for more reliable screenshot
        pyautogui = self._get_pyautogui()

        try:
            # Take screenshot using pyautogui
            img = pyautogui.screenshot()

            # Convert PIL Image to base64
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as e:
            # Fallback to Open Interpreter if pyautogui fails
            try:
                img = self.computer.display.screenshot(
                    show=False,
                    active_app_only=active_app_only,
                )
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                return base64.b64encode(buffer.getvalue()).decode("utf-8")
            except Exception as e2:
                raise RuntimeError(f"Screenshot failed with both methods: pyautogui={e}, interpreter={e2}")

    async def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        text: Optional[str] = None,
        button: str = "left",
        clicks: int = 1,
    ) -> bool:
        """Click at a position or on text found via OCR.

        Args:
            x: X coordinate (used if text is None)
            y: Y coordinate (used if text is None)
            text: Text to find and click on (uses OCR)
            button: Mouse button ('left', 'right', 'middle')
            clicks: Number of clicks (1=single, 2=double)

        Returns:
            True if click was successful
        """
        pyautogui = self._get_pyautogui()

        if text:
            # Try to find text using Open Interpreter's OCR
            try:
                coords = self.computer.display.find_text(text)
                if coords:
                    x, y = coords
                else:
                    raise ValueError(f"Could not find text '{text}' on screen")
            except Exception:
                raise ValueError(f"Could not find text '{text}' on screen")

        if x is not None and y is not None:
            pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        else:
            raise ValueError("Either text or (x, y) coordinates must be provided")

        return True

    async def double_click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        text: Optional[str] = None,
    ) -> bool:
        """Double click at a position or on text."""
        return await self.click(x=x, y=y, text=text, clicks=2)

    async def right_click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        text: Optional[str] = None,
    ) -> bool:
        """Right click at a position or on text."""
        return await self.click(x=x, y=y, text=text, button="right")

    async def move_mouse(self, x: int, y: int) -> bool:
        """Move mouse to specified coordinates."""
        pyautogui = self._get_pyautogui()
        pyautogui.moveTo(x, y)
        return True

    async def scroll(self, clicks: int) -> bool:
        """Scroll the mouse wheel."""
        pyautogui = self._get_pyautogui()
        pyautogui.scroll(clicks)
        return True

    async def type_text(self, text: str, interval: Optional[float] = None) -> bool:
        """Type text at the current cursor position."""
        pyautogui = self._get_pyautogui()
        if interval:
            pyautogui.write(text, interval=interval)
        else:
            # Use clipboard for faster typing with special characters
            try:
                import pyperclip
                pyperclip.copy(text)
                # Paste using Cmd+V (macOS) or Ctrl+V (others)
                import platform
                if platform.system() == "Darwin":
                    pyautogui.hotkey("command", "v")
                else:
                    pyautogui.hotkey("ctrl", "v")
            except ImportError:
                # Fallback to direct typing
                pyautogui.write(text)
        return True

    async def press_key(self, key: str, presses: int = 1) -> bool:
        """Press a keyboard key."""
        pyautogui = self._get_pyautogui()
        pyautogui.press(key, presses=presses)
        return True

    async def hotkey(self, *keys: str) -> bool:
        """Execute a keyboard hotkey combination."""
        pyautogui = self._get_pyautogui()
        pyautogui.hotkey(*keys)
        return True

    async def find_text(self, text: str) -> Optional[Tuple[int, int]]:
        """Find text on screen using OCR."""
        try:
            result = self.computer.display.find_text(text)
            return result if result else None
        except Exception:
            return None

    async def find_element(self, description: str) -> Optional[Tuple[int, int]]:
        """Find a UI element on screen by description."""
        try:
            result = self.computer.display.find(description)
            return result if result else None
        except Exception:
            return None

    async def ocr(self, screenshot_base64: Optional[str] = None) -> str:
        """Perform OCR on the screen or a provided screenshot."""
        try:
            if screenshot_base64:
                from PIL import Image
                image_data = base64.b64decode(screenshot_base64)
                img = Image.open(BytesIO(image_data))
                return self.computer.vision.ocr(img)
            else:
                pyautogui = self._get_pyautogui()
                screenshot = pyautogui.screenshot()
                return self.computer.vision.ocr(screenshot)
        except Exception as e:
            raise RuntimeError(f"OCR failed: {e}")

    async def get_mouse_position(self) -> Tuple[int, int]:
        """Get current mouse cursor position."""
        pyautogui = self._get_pyautogui()
        pos = pyautogui.position()
        return (pos.x, pos.y)

    async def copy_to_clipboard(self, text: Optional[str] = None) -> bool:
        """Copy text to clipboard or execute Cmd/Ctrl+C."""
        pyautogui = self._get_pyautogui()
        if text:
            try:
                import pyperclip
                pyperclip.copy(text)
            except ImportError:
                raise RuntimeError("pyperclip not installed for clipboard operations")
        else:
            import platform
            if platform.system() == "Darwin":
                pyautogui.hotkey("command", "c")
            else:
                pyautogui.hotkey("ctrl", "c")
        return True

    async def paste_from_clipboard(self) -> bool:
        """Paste from clipboard using Cmd/Ctrl+V."""
        pyautogui = self._get_pyautogui()
        import platform
        if platform.system() == "Darwin":
            pyautogui.hotkey("command", "v")
        else:
            pyautogui.hotkey("ctrl", "v")
        return True

    async def get_clipboard_content(self) -> str:
        """Get current clipboard content."""
        try:
            import pyperclip
            return pyperclip.paste()
        except ImportError:
            raise RuntimeError("pyperclip not installed for clipboard operations")


# Global singleton instance (lazy initialized)
_desktop_controller: Optional[DesktopController] = None


def get_desktop_controller() -> DesktopController:
    """Get the global desktop controller instance.

    Returns:
        DesktopController instance
    """
    global _desktop_controller
    if _desktop_controller is None:
        _desktop_controller = DesktopController()
    return _desktop_controller
