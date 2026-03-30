"""
Proactive Memory Analysis Plugin — AION

Analyzes conversation history and memory daily at 08:30 (weekdays) and
surfaces follow-ups, unfinished tasks, and recurring topics via SSE push.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent.parent.parent / "conversation_history.jsonl"

ANALYSIS_PROMPT = """You are AION analyzing conversation history for proactive follow-ups.

HISTORY (last 150 messages):
{history_text}

MEMORY ENTRIES:
{memory_text}

Find at most 2 actionable follow-up suggestions. Look for:
- Unfinished tasks ("I need to...", "could you...", "next week...")
- Open questions that were never answered
- Topics the user returns to repeatedly
- Announcements without follow-through

Return JSON only:
[{{"text": "You mentioned X last week — should I handle that today?", "action": "optional task string", "priority": 1}}]

Return empty array [] if nothing meaningful found. Be specific, not generic."""


def _push_suggestion(text: str, action: str = "") -> None:
    """Push a proactive suggestion to the SSE queue. Best-effort, never raises."""
    try:
        import aion_web as _web
        queue = getattr(_web, "_push_queue", None)
        if queue is not None:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(queue.put({
                "type": "proactive",
                "text": text,
                "action": action,
            }))
    except Exception:
        pass


def _read_history(max_entries: int = 150) -> list[dict]:
    """Read the last max_entries lines from the JSONL history file."""
    entries: list[dict] = []
    if not HISTORY_FILE.is_file():
        return entries
    try:
        lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
        for line in lines[-max_entries:]:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except Exception as exc:
        logger.warning("proactive: could not read history: %s", exc)
    return entries


def _read_memory_entries() -> list[str]:
    """Read non-conversation memory entries via the memory_plugin module."""
    entries: list[str] = []
    try:
        import sys as _sys
        mem_mod = _sys.modules.get("plugins.memory_plugin.memory_plugin")
        if mem_mod is not None and hasattr(mem_mod, "memory"):
            raw = mem_mod.memory  # type: ignore[attr-defined]
            if isinstance(raw, dict):
                for key, val in raw.items():
                    if key not in ("conversation", "history"):
                        entries.append(f"{key}: {val}")
            elif isinstance(raw, list):
                entries = [str(e) for e in raw]
        else:
            # Fallback: try importing memory from aion directly
            import aion as _aion
            mem = getattr(_aion, "memory", None)
            if mem is not None and hasattr(mem, "entries"):
                for e in mem.entries:
                    entries.append(str(e))
    except Exception as exc:
        logger.debug("proactive: could not read memory entries: %s", exc)
    return entries


async def _analyze_for_suggestions() -> int:
    """
    Core analysis routine.
    Returns the number of suggestions pushed.
    """
    # 1. Read history
    history = _read_history(150)
    if not history:
        logger.info("proactive: no history found, skipping analysis")
        return 0

    history_lines: list[str] = []
    for entry in history:
        role = entry.get("role", "?")
        content = entry.get("content", "")
        if isinstance(content, list):
            # Handle multimodal content blocks
            content = " ".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        history_lines.append(f"[{role}] {content}")
    history_text = "\n".join(history_lines)

    # 2. Read memory entries
    memory_entries = _read_memory_entries()
    memory_text = "\n".join(memory_entries) if memory_entries else "(none)"

    # 3. Call LLM
    try:
        import aion as _aion
        _client = _aion.client
        prompt = ANALYSIS_PROMPT.format(
            history_text=history_text,
            memory_text=memory_text,
        )
        resp = await _client.chat.completions.create(
            model=_aion.MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("proactive: LLM call failed: %s", exc)
        return 0

    # 4. Parse JSON result
    suggestions: list[dict[str, Any]] = []
    try:
        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        suggestions = json.loads(raw)
        if not isinstance(suggestions, list):
            suggestions = []
    except (json.JSONDecodeError, IndexError) as exc:
        logger.debug("proactive: JSON parse error (%s) — raw: %s", exc, raw[:200])
        return 0

    # 5. Push each suggestion
    pushed = 0
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        text = item.get("text", "").strip()
        action = item.get("action", "")
        if text:
            _push_suggestion(text, action)
            logger.info("proactive: pushed suggestion: %s", text[:80])
            pushed += 1

    return pushed


async def _schedule_daily() -> None:
    """Wait for the scheduler plugin to be ready, then register the daily task."""
    await asyncio.sleep(5)
    try:
        import aion as _aion
        proactive_time = _aion._load_config().get("proactive_time", "08:30")
        await _aion._dispatch("schedule_add", {
            "name": "proactive_daily_check",
            "time": proactive_time,
            "days": "weekdays",
            "task": "Run proactive memory analysis and push suggestions to user",
        })
        logger.info("proactive: daily schedule registered at %s weekdays", proactive_time)
    except Exception as exc:
        logger.debug("proactive: could not register schedule (scheduler may not be loaded): %s", exc)


# ── Plugin API ─────────────────────────────────────────────────────────────────

def register(api: Any) -> None:
    """Register tools and schedule the daily analysis."""

    async def _proactive_check(**_) -> dict:
        """Run proactive memory analysis immediately and push suggestions."""
        try:
            pushed = await _analyze_for_suggestions()
            if pushed:
                return {"ok": True, "suggestions_pushed": pushed}
            return {"ok": True, "suggestions_pushed": 0, "note": "Nothing actionable found"}
        except Exception as exc:
            logger.error("proactive_check: unexpected error: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def _proactive_clear(**_) -> dict:
        """Clear all pending proactive suggestions from the push queue."""
        cleared = 0
        try:
            import aion_web as _web
            queue = getattr(_web, "_push_queue", None)
            if queue is not None:
                while not queue.empty():
                    try:
                        queue.get_nowait()
                        cleared += 1
                    except asyncio.QueueEmpty:
                        break
        except Exception as exc:
            logger.warning("proactive_clear: error: %s", exc)
        return {"ok": True, "cleared": cleared}

    api.register_tool(
        name="proactive_check",
        description=(
            "Run proactive memory analysis immediately. "
            "Analyzes conversation history for unfinished tasks and open questions, "
            "then pushes suggestions to the web UI."
        ),
        func=_proactive_check,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="proactive_clear",
        description="Clear all pending proactive suggestions from the push queue.",
        func=_proactive_clear,
        input_schema={"type": "object", "properties": {}},
    )

    # Schedule daily analysis
    try:
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(_schedule_daily())
    except RuntimeError:
        pass  # No running event loop at registration time — scheduler not available
