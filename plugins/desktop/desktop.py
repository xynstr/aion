"""
desktop — Desktop automation tools via pyautogui and Pillow.

Provides screenshot, mouse control, keyboard input, and hotkeys.
Destructive actions (click, drag, type, hotkey) require explicit confirmation.

Setup:
    pip install pyautogui Pillow
    pip install pyperclip   # optional — enables unicode text input

Platform notes:
  macOS   — requires Accessibility permission:
             System Settings → Privacy & Security → Accessibility → enable Terminal/Python
  Linux   — requires a display (DISPLAY or WAYLAND_DISPLAY) and optionally xclip/xdotool
  Windows — works out of the box; pyperclip enables full unicode typing
"""

import io
import base64
import sys
import os


def register(api):

    # ── Platform / environment checks ────────────────────────────────────────

    # Headless Linux — bail out early (no display server available)
    if sys.platform == "linux" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("[desktop] Headless Linux environment — desktop tools disabled.")
        return

    # macOS — check Accessibility permission early so errors are informative
    if sys.platform == "darwin":
        try:
            import pyautogui as _pag_check  # noqa: F401
            _pag_check.position()           # triggers permission check
        except Exception as _mac_err:
            _msg = str(_mac_err)
            if "accessibility" in _msg.lower() or "permission" in _msg.lower() or "axerror" in _msg.lower():
                print(
                    "[desktop] macOS: Accessibility permission missing.\n"
                    "          → System Settings → Privacy & Security → Accessibility\n"
                    "          → Enable Terminal (or your Python environment)."
                )
                return
            # Other errors (pyautogui not installed) — let individual tools handle it

    # ── pyautogui global settings ─────────────────────────────────────────────
    # Applied once on first actual import; re-applied every registration call is harmless.
    try:
        import pyautogui as _pag
        _pag.PAUSE     = 0.05   # 50 ms pause between actions (default: 100 ms)
        _pag.FAILSAFE  = True   # move mouse to top-left corner to abort — keep enabled
    except ImportError:
        pass  # individual tools will show the install hint

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _paste_key():
        """Return the correct paste modifier for the current platform."""
        return "command" if sys.platform == "darwin" else "ctrl"

    def _type_unicode(pyautogui, text: str) -> None:
        """
        Type arbitrary text including unicode.
        Strategy:
          1. Try pyperclip (cross-platform clipboard) → paste via Ctrl/Cmd+V
          2. Fall back to pyautogui.typewrite (ASCII only)
        """
        try:
            import pyperclip
            pyperclip.copy(text)
            import time; time.sleep(0.05)
            pyautogui.hotkey(_paste_key(), "v")
        except ImportError:
            # No pyperclip — strip to ASCII and warn
            ascii_text = text.encode("ascii", errors="replace").decode("ascii")
            pyautogui.typewrite(ascii_text, interval=0.02)

    def _scale_image(img, scale: float):
        """Return a PIL image scaled to `scale` (0 < scale ≤ 1.0)."""
        if scale >= 1.0:
            return img
        new_w = max(1, int(img.width * scale))
        new_h = max(1, int(img.height * scale))
        try:
            from PIL import Image as _PILImage
            return img.resize((new_w, new_h), _PILImage.LANCZOS)
        except Exception:
            return img.resize((new_w, new_h))

    # ── Tool implementations ──────────────────────────────────────────────────

    async def _desktop_screenshot(scale: float = 1.0, **_):
        """
        Take a full-screen screenshot.
        scale: 0.1–1.0 — reduce resolution before encoding (useful for LLM vision, saves tokens).
        Note: captures the primary monitor only on multi-monitor setups.
        """
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            scale = max(0.1, min(1.0, float(scale)))
            screenshot = pyautogui.screenshot()
            if scale < 1.0:
                screenshot = _scale_image(screenshot, scale)
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG", optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return {
                "ok": True,
                "image": f"data:image/png;base64,{b64}",
                "width": screenshot.width,
                "height": screenshot.height,
                "scale": scale,
            }
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_get_screen_size(**_):
        """Return the screen resolution without taking a screenshot."""
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            w, h = pyautogui.size()
            return {"ok": True, "width": w, "height": h}
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

    async def _desktop_move_mouse(x: int = 0, y: int = 0, duration: float = 0.3, **_):
        """Move the mouse cursor to the given coordinates without clicking."""
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            pyautogui.moveTo(x, y, duration=max(0.0, duration))
            return {"ok": True, "position": [x, y]}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_click(x: int = 0, y: int = 0,
                             button: str = "left", clicks: int = 1,
                             confirmed: bool = False, **_):
        """Click at screen coordinates. Use clicks=2 for double-click. Requires confirmation."""
        if not confirmed:
            label = "Double-click" if clicks == 2 else "Click"
            return {
                "status": "approval_required",
                "message": (
                    f"{label} at ({x}, {y}) with button '{button}'. "
                    "Confirm with confirmed=true to execute."
                ),
            }
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            pyautogui.click(x, y, button=button, clicks=max(1, clicks))
            return {"ok": True, "clicked": [x, y], "button": button, "clicks": clicks}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_drag(
        x1: int = 0, y1: int = 0,
        x2: int = 0, y2: int = 0,
        duration: float = 0.5,
        button: str = "left",
        confirmed: bool = False,
        **_,
    ):
        """Drag from (x1, y1) to (x2, y2). Requires confirmation."""
        if not confirmed:
            return {
                "status": "approval_required",
                "message": (
                    f"Drag from ({x1}, {y1}) to ({x2}, {y2}) with {button} button "
                    f"over {duration}s. Confirm with confirmed=true to execute."
                ),
            }
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            pyautogui.moveTo(x1, y1, duration=0.2)
            pyautogui.dragTo(x2, y2, duration=max(0.1, duration), button=button)
            return {"ok": True, "from": [x1, y1], "to": [x2, y2]}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_scroll(
        direction: str = "down", amount: int = 3,
        x: int = None, y: int = None,
        **_,
    ):
        """Scroll the mouse wheel. Optionally move to (x, y) first."""
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            if x is not None and y is not None:
                pyautogui.moveTo(x, y, duration=0.2)
            clicks = abs(amount) if direction == "up" else -abs(amount)
            pyautogui.scroll(clicks)
            return {"ok": True, "scrolled": direction, "clicks": abs(amount)}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_type(text: str = "", confirmed: bool = False, **_):
        """
        Type text at the current cursor position.
        Supports unicode (ä, ö, ü, emoji, …) when pyperclip is installed.
        Requires confirmation.
        """
        if not confirmed:
            preview = text[:60] + ("…" if len(text) > 60 else "")
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
            _type_unicode(pyautogui, text)
            return {"ok": True, "typed_chars": len(text)}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_key_press(key: str = "", confirmed: bool = False, **_):
        """
        Press and release a single key (e.g. 'enter', 'tab', 'escape', 'delete', 'f5').
        Use desktop_hotkey for key combinations.
        Requires confirmation for potentially destructive keys (delete, f-keys, escape).
        """
        SENSITIVE_KEYS = {"delete", "backspace", "escape", "f1", "f2", "f3", "f4",
                          "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12"}
        if not key:
            return {"error": "No key provided."}

        needs_confirmation = key.lower() in SENSITIVE_KEYS
        if needs_confirmation and not confirmed:
            return {
                "status": "approval_required",
                "message": (
                    f"Press key '{key}'. "
                    "Confirm with confirmed=true to execute."
                ),
            }
        try:
            import pyautogui
        except ImportError:
            return {"error": "pyautogui not installed. Run: pip install pyautogui Pillow"}
        try:
            pyautogui.press(key)
            return {"ok": True, "key": key}
        except Exception as e:
            return {"error": str(e)}

    async def _desktop_hotkey(keys: list = None, confirmed: bool = False, **_):
        """Press a key combination. Requires confirmation for ctrl/alt/win/cmd keys."""
        if keys is None:
            keys = []
        if not keys:
            return {"error": "No keys provided."}

        sensitive = {"ctrl", "alt", "win", "cmd", "command"}
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

    # ── Tool registrations ────────────────────────────────────────────────────

    api.register_tool(
        name="desktop_screenshot",
        description=(
            "Take a full-screen screenshot. Returns a base64-encoded PNG with width and height. "
            "Use scale=0.5 to halve resolution (faster, fewer tokens for vision models). "
            "Note: captures primary monitor only on multi-monitor setups."
        ),
        func=_desktop_screenshot,
        input_schema={
            "type": "object",
            "properties": {
                "scale": {
                    "type": "number",
                    "description": "Resolution scale factor 0.1–1.0 (default 1.0 = full resolution). Use 0.5 to reduce size for vision models.",
                    "default": 1.0,
                },
            },
        },
    )

    api.register_tool(
        name="desktop_get_screen_size",
        description="Return the screen resolution (width and height in pixels) without taking a screenshot.",
        func=_desktop_get_screen_size,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="desktop_get_mouse_position",
        description="Return the current mouse cursor position as {ok, x, y}.",
        func=_desktop_get_mouse_position,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="desktop_move_mouse",
        description="Move the mouse cursor to screen coordinates (x, y) without clicking.",
        func=_desktop_move_mouse,
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Target X coordinate"},
                "y": {"type": "integer", "description": "Target Y coordinate"},
                "duration": {
                    "type": "number",
                    "description": "Movement duration in seconds (default 0.3)",
                    "default": 0.3,
                },
            },
            "required": ["x", "y"],
        },
    )

    api.register_tool(
        name="desktop_click",
        description=(
            "Click at screen coordinates (x, y). "
            "Use clicks=2 for double-click. "
            "Requires confirmed=true to execute."
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
                    "description": "Mouse button",
                },
                "clicks": {
                    "type": "integer",
                    "default": 1,
                    "description": "Number of clicks (1 = single, 2 = double)",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Set true to execute (required)",
                    "default": False,
                },
            },
            "required": ["x", "y"],
        },
    )

    api.register_tool(
        name="desktop_drag",
        description=(
            "Drag the mouse from (x1, y1) to (x2, y2). "
            "Useful for moving windows, sliders, and drag-and-drop. "
            "Requires confirmed=true to execute."
        ),
        func=_desktop_drag,
        input_schema={
            "type": "object",
            "properties": {
                "x1": {"type": "integer", "description": "Start X coordinate"},
                "y1": {"type": "integer", "description": "Start Y coordinate"},
                "x2": {"type": "integer", "description": "End X coordinate"},
                "y2": {"type": "integer", "description": "End Y coordinate"},
                "duration": {
                    "type": "number",
                    "default": 0.5,
                    "description": "Drag duration in seconds (default 0.5)",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "default": "left",
                    "description": "Mouse button to hold during drag",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Set true to execute (required)",
                    "default": False,
                },
            },
            "required": ["x1", "y1", "x2", "y2"],
        },
    )

    api.register_tool(
        name="desktop_scroll",
        description="Scroll the mouse wheel up or down. Optionally move to (x, y) first.",
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
                "x": {"type": "integer", "description": "Move mouse to X before scrolling (optional)"},
                "y": {"type": "integer", "description": "Move mouse to Y before scrolling (optional)"},
            },
        },
    )

    api.register_tool(
        name="desktop_type",
        description=(
            "Type text at the current cursor position. "
            "Supports unicode (umlauts, emoji, …) when pyperclip is installed. "
            "Requires confirmed=true to execute."
        ),
        func=_desktop_type,
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type (unicode supported)"},
                "confirmed": {
                    "type": "boolean",
                    "description": "Set true to execute (required)",
                    "default": False,
                },
            },
            "required": ["text"],
        },
    )

    api.register_tool(
        name="desktop_key_press",
        description=(
            "Press and release a single keyboard key "
            "(e.g. 'enter', 'tab', 'escape', 'delete', 'space', 'up', 'down', 'f5'). "
            "For key combinations use desktop_hotkey instead. "
            "Requires confirmed=true for potentially destructive keys (delete, f-keys, escape)."
        ),
        func=_desktop_key_press,
        input_schema={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key name: 'enter', 'tab', 'escape', 'space', 'delete', 'backspace', 'up', 'down', 'left', 'right', 'f1'–'f12', etc.",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Set true to execute (required for delete/escape/f-keys)",
                    "default": False,
                },
            },
            "required": ["key"],
        },
    )

    api.register_tool(
        name="desktop_hotkey",
        description=(
            "Press a key combination simultaneously (e.g. ['ctrl', 'c'] to copy). "
            "Use desktop_key_press for single keys. "
            "Requires confirmed=true when combination includes ctrl, alt, win, or cmd."
        ),
        func=_desktop_hotkey,
        input_schema={
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keys to press simultaneously, e.g. ['ctrl', 'c'] or ['alt', 'f4']",
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
