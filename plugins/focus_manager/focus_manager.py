"""
AION Focus Manager — Working memory / task focus.

Stores the current task focus in focus_state.json.
Injected into every turn's system prompt via aion_session.py so AION
never loses track of what it is supposed to be working on.
"""
import json
from pathlib import Path

_FOCUS_FILE = Path(__file__).parent / "focus_state.json"


# ── Public API used by aion_session.py ────────────────────────────────────────

def get_current_focus_for_prompt() -> str | None:
    """Return the current focus text, or None if no focus is set.

    Called once per turn by aion_session.py to inject focus into the
    effective system prompt. Must be fast and never raise.
    """
    try:
        if not _FOCUS_FILE.exists():
            return None
        data = json.loads(_FOCUS_FILE.read_text(encoding="utf-8"))
        return data.get("current_focus") or None
    except Exception:
        return None


# ── Tool implementations ───────────────────────────────────────────────────────

def _focus_set(task: str, **_) -> dict:
    try:
        _FOCUS_FILE.write_text(
            json.dumps({"current_focus": task.strip()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"ok": True, "focus": task.strip(),
                "message": f"Focus set: {task.strip()!r}"}
    except Exception as e:
        return {"error": str(e)}


def _focus_get(**_) -> dict:
    focus = get_current_focus_for_prompt()
    if focus:
        return {"ok": True, "current_focus": focus}
    return {"ok": True, "current_focus": None, "message": "No focus set."}


def _focus_clear(**_) -> dict:
    try:
        if _FOCUS_FILE.exists():
            _FOCUS_FILE.unlink()
        return {"ok": True, "message": "Focus cleared."}
    except Exception as e:
        return {"error": str(e)}


# ── Plugin registration ────────────────────────────────────────────────────────

def register(api) -> None:
    api.register_tool(
        name="focus_set",
        description="Set the current task focus. Injected into every turn until cleared. Use at the start of multi-step tasks.",
        func=_focus_set,
        input_schema={
            "type": "object",
            "properties": {
                "task": {"type": "string",
                         "description": "Short description of the current task/goal."},
            },
            "required": ["task"],
        },
    )

    api.register_tool(
        name="focus_get",
        description="Return the currently active focus/task, or report that no focus is set.",
        func=_focus_get,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="focus_clear",
        description="Clear the current focus. Call this when the task is done.",
        func=_focus_clear,
        input_schema={"type": "object", "properties": {}},
    )

    print("[focus_manager] loaded — focus_set / focus_get / focus_clear")
