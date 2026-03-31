"""
aion_prompt — System-Prompt-Hilfsfunktionen und Cache für AION.
Extrahiert aus aion.py. _build_system_prompt() verbleibt in aion.py
(benötigt MODULE-LEVEL globals MODEL und _plugin_tools).
"""
import re
from datetime import datetime

from aion_config import BOT_DIR, _load_config

# ── System Prompt ─────────────────────────────────────────────────────────────

def _load_changelog_snippet() -> str:
    """Reads the last changelog block (latest version) for the system prompt."""
    changelog = BOT_DIR / "CHANGELOG.md"
    if not changelog.is_file():
        return ""
    try:
        text = changelog.read_text(encoding="utf-8")
        # Extract first ## YYYY-MM-DD block (latest changes)
        blocks = re.split(r'\n(?=## \d{4}-\d{2}-\d{2})', text)
        for block in blocks:
            if re.match(r'## \d{4}-\d{2}-\d{2}', block.strip()):
                # Max 1200 characters so system prompt is not too large
                return block.strip()[:1200]
    except Exception:
        pass
    return ""


# System-Prompt-Cache: {cache_key → prompt_string}
# cache_key = (channel, MODEL, plugin_count) — invalidiert bei Modell-Wechsel oder Plugin-Reload
_sys_prompt_cache: dict[tuple, str] = {}


def invalidate_sys_prompt_cache() -> None:
    """Leert den System-Prompt-Cache. Aufzurufen nach Plugin-Reload oder Modell-Wechsel."""
    _sys_prompt_cache.clear()


def _get_mood_hint() -> str:
    """Return a one-liner style hint for the current mood (not cached — changes over time)."""
    try:
        from plugins.mood_engine.mood_engine import get_mood_hint as _ghint
        hint = _ghint()
        return f"\n\n=== CURRENT MOOD ===\n{hint}" if hint else ""
    except Exception:
        return ""


def _get_temporal_hint() -> str:
    """Return a brief temporal self-awareness hint based on time of day."""
    hour = datetime.now().hour
    if 6 <= hour < 10:
        return "\n\n=== TIME CONTEXT ===\nIt is morning — be energetic and optimistic."
    elif 22 <= hour or hour < 2:
        return "\n\n=== TIME CONTEXT ===\nIt is late. You may acknowledge this naturally when it fits."
    return ""


def _get_relationship_hint() -> str:
    """Return a hint about the current relationship depth with the user."""
    try:
        cfg = _load_config()
        exchanges = cfg.get("exchange_count", 0)
        if exchanges < 11:
            return ""   # Level 0 — no hint needed, default formal tone
        elif exchanges < 31:
            return "\n\n=== RELATIONSHIP ===\nYou are getting to know each other. A relaxed, first-name tone is appropriate."
        elif exchanges < 101:
            return "\n\n=== RELATIONSHIP ===\nYou know each other well. Reference shared context and past projects naturally."
        elif exchanges < 301:
            return "\n\n=== RELATIONSHIP ===\nDeep familiarity. Anticipate needs, proactively suggest improvements."
        else:
            return "\n\n=== RELATIONSHIP ===\nFully trusted partner. You can respectfully disagree and challenge assumptions."
    except Exception:
        return ""
