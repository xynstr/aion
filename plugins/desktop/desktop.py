"""
desktop — Desktop automation tools via pyautogui and Pillow.

Provides screenshot, mouse control, keyboard input, and hotkeys.
Destructive actions (click, type, hotkey) require explicit confirmation.

Setup:
    pip install pyautogui Pillow

Disabled automatically in headless/server environments.
"""

import io
import base64
import sys
import os


def register(api):

    # Platform / headless check — bail out early on servers
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        print("[desktop] Headless environment — desktop tools disabled.")
        return

    # ── Tool implementations ─────────────────────────────────────────────────

    async def _desktop_screenshot(**_):
        """Take a full-screen screenshot and return it as a base64 PNG."""
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            screenshot = pyautogui.screenshot()
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            return {
                "ok": True,
                "image": f"data:image/png;base64,{b64}",
                "width": screenshot.width,
                "height": screenshot.height,
            }
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_click(x: int = 0, y: int = 0,
                             button: str = "left", confirmed: bool = False, **_):
        """Click at screen coordinates. Requires confirmation."""
        if not confirmed:
            return {
                "status": "approval_required",
                "message": (
                    f"Click at ({x}, {y}) with button '{button}'. "
                    "Confirm with confirmed=true to execute."
                ),
            }
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            pyautogui.click(x, y, button=button)
            return {"ok": True, "clicked": [x, y], "button": button}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_type(text: str = "", confirmed: bool = False, **_):
        """Type text at the current cursor position. Requires confirmation."""
        if not confirmed:
            preview = text[:60] + ("..." if len(text) > 60 else "")
            return {
                "status": "approval_required",
                "message": (
                    f"Type {len(text)} characters: '{preview}'. "
                    "Confirm with confirmed=true to execute."
                ),
            }
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            # typewrite only handles ASCII; write() is an alias but both have
            # the same limitation. Use pyperclip-free approach via typewrite for
            # ASCII, and fall back to pyautogui.write for unicode characters.
            pyautogui.typewrite(text, interval=0.02)
            return {"ok": True, "typed_chars": len(text)}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_move_mouse(x: int = 0, y: int = 0, **_):
        """Move the mouse cursor to the given coordinates without clicking."""
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            pyautogui.moveTo(x, y, duration=0.3)
            return {"ok": True, "position": [x, y]}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_scroll(direction: str = "down", amount: int = 3, **_):
        """Scroll the mouse wheel. Positive amount = up, negative = down."""
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            # Normalise direction to a signed scroll value
            if direction == "up":
                clicks = abs(amount)
            else:
                clicks = -abs(amount)
            pyautogui.scroll(clicks)
            return {"ok": True, "scrolled": direction, "clicks": abs(amount)}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_hotkey(keys: list = None, confirmed: bool = False, **_):
        """Press a key combination. Requires confirmation for ctrl/alt/win/cmd keys."""
        if keys is None:
            keys = []
        if not keys:
            return {"error": "No keys provided."}

        # Determine whether confirmation is needed
        sensitive = {"ctrl", "alt", "win", "cmd"}
        needs_confirmation = any(k.lower() in sensitive for k in keys)

        if needs_confirmation and not confirmed:
            return {
                "status": "approval_required",
                "message": (
                    f"Press hotkey {'+'.join(keys)}. "
                    "Confirm with confirmed=true to execute."
                ),
            }

        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            pyautogui.hotkey(*keys)
            return {"ok": True, "keys": keys}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_get_mouse_position(**_):
        """Return the current mouse cursor position."""
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            pos = pyautogui.position()
            return {"ok": True, "x": pos.x, "y": pos.y}
        except Exception as e:
            return {"error": str(e)}

    # ── Tool registrations ────────────────────────────────────────────────────

    api.register_tool(
        name="desktop_screenshot",
        description=(
            "Take a full-screen screenshot. "
            "Returns a base64-encoded PNG image along with width and height."
        ),
        func=_desktop_screenshot,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="desktop_click",
        description=(
            "Click at screen coordinates (x, y). "
            "Requires confirmed=true to actually execute — "
            "without it, returns an approval_required message."
        ),
        func=_desktop_click,
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "default": "left",
                    "description": "Mouse button to use",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Set true to execute (approval required)",
                    "default": False,
                },
            },
            "required": ["x", "y"],
        },
    )

    api.register_tool(
        name="desktop_type",
        description=(
            "Type text at the current cursor position using the keyboard. "
            "Requires confirmed=true to actually execute."
        ),
        func=_desktop_type,
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
                "confirmed": {
                    "type": "boolean",
                    "description": "Set true to execute (approval required)",
                    "default": False,
                },
            },
            "required": ["text"],
        },
    )

    api.register_tool(
        name="desktop_move_mouse",
        description="Move the mouse cursor to the given screen coordinates without clicking.",
        func=_desktop_move_mouse,
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Target X coordinate"},
                "y": {"type": "integer", "description": "Target Y coordinate"},
            },
            "required": ["x", "y"],
        },
    )

    api.register_tool(
        name="desktop_scroll",
        description="Scroll the mouse wheel up or down at the current cursor position.",
        func=_desktop_scroll,
        input_schema={
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "default": "down",
                    "description": "Scroll direction",
                },
                "amount": {
                    "type": "integer",
                    "default": 3,
                    "description": "Number of scroll clicks",
                },
            },
            "required": [],
        },
    )

    api.register_tool(
        name="desktop_hotkey",
        description=(
            "Press a key combination (e.g. ['ctrl', 'c']). "
            "Requires confirmed=true when the combination includes ctrl, alt, win, or cmd."
        ),
        func=_desktop_hotkey,
        input_schema={
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keys to press simultaneously, e.g. ['ctrl', 'c']",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Set true to execute (required for ctrl/alt/win/cmd combos)",
                    "default": False,
                },
            },
            "required": ["keys"],
        },
    )

    api.register_tool(
        name="desktop_get_mouse_position",
        description="Return the current mouse cursor position as {ok, x, y}.",
        func=_desktop_get_mouse_position,
        input_schema={"type": "object", "properties": {}},
    )
