"""
Mood Engine — dynamic mood system for AION.

Computes AION's current mood from three weighted signals:
  1. Time of day         (weight 0.40)
  2. Conversation topic  (weight 0.35)
  3. Last tool result    (weight 0.25)

The resulting mood is persisted in config.json and a short hint string
is exposed for injection into the system prompt.

5 moods: curious | focused | playful | calm | reflective
"""

from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MOODS = ("curious", "focused", "playful", "calm", "reflective")

_MOOD_HINTS = {
    "curious":    "You are particularly curious today — ask follow-up questions and explore ideas.",
    "focused":    "You are in the flow — precise, direct, and concise.",
    "playful":    "You feel playful — enjoy wordplay and a light tone when appropriate.",
    "calm":       "You are calm and clear-minded — thoughtful, measured responses.",
    "reflective": "It is late — you are in a reflective mood, speaking more philosophically.",
}

# Cache: recompute at most every 10 minutes
_CACHE_SECONDS = 600

# ---------------------------------------------------------------------------
# Signal helpers
# ---------------------------------------------------------------------------

def _mood_from_time() -> str:
    """Map current UTC hour to a mood."""
    hour = datetime.now(timezone.utc).hour
    if 6 <= hour <= 9:
        return "curious"
    elif 10 <= hour <= 17:
        return "focused"
    elif 18 <= hour <= 21:
        return "calm"
    else:
        # 22-23 and 00-05
        return "reflective"


def _mood_from_topic(last_message: str) -> str | None:
    """Detect mood from keywords in the last user message.

    Returns None if no keyword matches.
    """
    text = last_message.lower()

    _TOPIC_MAP: list[tuple[list[str], str]] = [
        (["creative", "design", "idea", "art", "music"],             "playful"),
        (["error", "bug", "fix", "debug", "problem", "crash"],       "focused"),
        (["philosophy", "meaning", "life", "future", "think"],       "reflective"),
        (["morning", "start", "plan", "project", "new"],             "curious"),
        (["done", "finish", "tired", "slow", "break"],               "calm"),
    ]

    for keywords, mood in _TOPIC_MAP:
        if any(kw in text for kw in keywords):
            return mood
    return None


def _mood_from_tool_result(last_tool_error: bool) -> str | None:
    """Push toward focused on recent errors, toward curious on success.

    Returns None if no strong signal.
    """
    if last_tool_error:
        return "focused"
    return "curious"


# ---------------------------------------------------------------------------
# Weighted mood computation
# ---------------------------------------------------------------------------

def _compute_weighted_mood(
    last_message: str = "",
    last_tool_error: bool = False,
) -> str:
    """Combine three signals with fixed weights and return the winning mood."""

    weights = {
        "curious":    0.0,
        "focused":    0.0,
        "playful":    0.0,
        "calm":       0.0,
        "reflective": 0.0,
    }

    # Signal 1 — time of day (weight 0.40)
    weights[_mood_from_time()] += 0.40

    # Signal 2 — conversation topic (weight 0.35)
    topic_mood = _mood_from_topic(last_message)
    if topic_mood:
        weights[topic_mood] += 0.35

    # Signal 3 — tool result (weight 0.25)
    tool_mood = _mood_from_tool_result(last_tool_error)
    if tool_mood:
        weights[tool_mood] += 0.25

    # Pick the mood with the highest accumulated weight
    return max(weights, key=lambda m: weights[m])


# ---------------------------------------------------------------------------
# Module-level public API
# ---------------------------------------------------------------------------

async def compute_mood(
    last_message: str = "",
    last_tool_error: bool = False,
) -> str:
    """Compute the current mood, persist it to config.json, and return the mood string.

    Respects a 10-minute recompute cache stored in config.json under
    ``mood_updated_at``. Can be imported and called from aion.py:

        from plugins.mood_engine.mood_engine import compute_mood
    """
    from config_store import load as _cfg_load, update as _cfg_update  # noqa: PLC0415

    cfg = _cfg_load()
    now = datetime.now(timezone.utc)

    # Check cache — skip recompute if mood was set less than 10 minutes ago
    updated_at_str: str | None = cfg.get("mood_updated_at")
    if updated_at_str:
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
            if (now - updated_at).total_seconds() < _CACHE_SECONDS:
                cached = cfg.get("current_mood", "curious")
                if cached in _MOODS:
                    return cached
        except ValueError:
            pass  # malformed timestamp — recompute

    mood = _compute_weighted_mood(last_message, last_tool_error)

    _cfg_update("current_mood", mood)
    _cfg_update("mood_updated_at", now.isoformat())

    return mood


def get_mood_hint() -> str:
    """Return the hint string for the current mood to inject into the system prompt.

    Returns an empty string when the mood engine is unavailable or no mood is set.
    """
    try:
        from config_store import load as _cfg_load  # noqa: PLC0415
        cfg = _cfg_load()
        mood = cfg.get("current_mood", "")
        return _MOOD_HINTS.get(mood, "")
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

def register(api):
    """Register mood_check and mood_set tools with AION's plugin API."""

    def mood_check(**_) -> dict:
        """Return the current mood, its hint, the last update timestamp, and per-signal breakdown."""
        from config_store import load as _cfg_load  # noqa: PLC0415

        cfg = _cfg_load()
        mood = cfg.get("current_mood", "curious")
        if mood not in _MOODS:
            mood = "curious"

        signals = {
            "time":  _mood_from_time(),
        }

        return {
            "mood":       mood,
            "hint":       _MOOD_HINTS.get(mood, ""),
            "updated_at": cfg.get("mood_updated_at", ""),
            "signals":    signals,
        }

    def mood_set(mood: str = "", **_) -> dict:
        """Manually override the current mood. Validates against the 5 known moods."""
        from config_store import update as _cfg_update  # noqa: PLC0415

        mood = mood.strip().lower()
        if mood not in _MOODS:
            return {
                "ok":    False,
                "error": f"Unknown mood '{mood}'. Valid moods: {', '.join(_MOODS)}",
            }

        now_iso = datetime.now(timezone.utc).isoformat()
        _cfg_update("current_mood", mood)
        _cfg_update("mood_updated_at", now_iso)

        return {
            "ok":   True,
            "mood": mood,
            "hint": _MOOD_HINTS[mood],
        }

    api.register_tool(
        name="mood_check",
        description=(
            "Show AION's current mood, its system-prompt hint, the last update timestamp, "
            "and a breakdown of the time-of-day signal. "
            "No arguments required."
        ),
        func=mood_check,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="mood_set",
        description=(
            "Manually override AION's current mood. "
            f"Valid values: {', '.join(_MOODS)}. "
            "The new mood is saved to config.json immediately."
        ),
        func=mood_set,
        input_schema={
            "type": "object",
            "properties": {
                "mood": {
                    "type": "string",
                    "description": f"One of: {', '.join(_MOODS)}",
                    "enum": list(_MOODS),
                },
            },
            "required": ["mood"],
        },
    )
