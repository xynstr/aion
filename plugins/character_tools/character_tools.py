"""
character_tools — Direktes Lesen und Schreiben der character.md

Tools:
  character_read()                          → vollständigen Inhalt lesen
  character_update_section(section, text)   → Abschnitt ersetzen (oder anhängen)
  character_append_insight(insight)         → Schnell einen Eintrag in "My insights" anhängen
  character_set_user_knowledge(content)     → "What I know about my user" komplett ersetzen
"""

from __future__ import annotations
import re
from pathlib import Path
from datetime import datetime, timezone

UTC = timezone.utc
_BOT_DIR = Path(__file__).parent.parent.parent
CHARACTER_FILE = _BOT_DIR / "character.md"


# ── helpers ───────────────────────────────────────────────────────────────────

def _read() -> str:
    if CHARACTER_FILE.is_file():
        return CHARACTER_FILE.read_text(encoding="utf-8")
    return ""


def _write(content: str) -> None:
    CHARACTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHARACTER_FILE.write_text(content, encoding="utf-8")
    # Invalidate AION's system-prompt cache so next turn picks up changes
    try:
        import aion as _m
        _m._sys_prompt_cache.clear()
    except Exception:
        pass


def _find_section(text: str, section_name: str) -> tuple[int, int, int] | None:
    """
    Find a ## or ### section by name (case-insensitive).
    Returns (header_start, content_start, content_end) or None.
    content_end points to just before the next header of same/higher level,
    or end-of-string.
    """
    pattern = re.compile(
        r'^(#{1,3})\s+' + re.escape(section_name) + r'[^\n]*$',
        re.MULTILINE | re.IGNORECASE,
    )
    m = pattern.search(text)
    if not m:
        return None

    level = len(m.group(1))
    content_start = m.end()  # right after the header line

    # Next header of same or shallower level
    next_hdr = re.compile(r'^#{1,' + str(level) + r'}\s', re.MULTILINE)
    nm = next_hdr.search(text, content_start)
    content_end = nm.start() if nm else len(text)

    return m.start(), content_start, content_end


# ── tool handlers ─────────────────────────────────────────────────────────────

def character_read(_args: dict) -> dict:
    """Read the full contents of character.md."""
    content = _read()
    if not content:
        return {"ok": False, "error": "character.md not found or empty"}
    return {"ok": True, "content": content, "length": len(content)}


def character_update_section(args: dict) -> dict:
    """
    Replace the content of a named section in character.md.
    If the section doesn't exist, it is appended as a new ## section.

    Args:
        section (str): Section heading, e.g. "My insights", "What I know about my user"
        content (str): New content for the section (replaces everything under the heading)
    """
    section_name = (args.get("section") or "").strip()
    new_content   = (args.get("content") or "").strip()
    if not section_name:
        return {"ok": False, "error": "section parameter is required"}
    if not new_content:
        return {"ok": False, "error": "content parameter is required"}

    text = _read()
    result = _find_section(text, section_name)

    if result:
        header_start, content_start, content_end = result
        # Preserve header line, replace content beneath it
        header_line = text[header_start:content_start]
        updated = text[:content_start] + "\n" + new_content + "\n\n" + text[content_end:]
    else:
        # Section doesn't exist → append at end
        updated = text.rstrip() + f"\n\n## {section_name}\n\n{new_content}\n"

    _write(updated)
    return {"ok": True, "section": section_name, "chars_written": len(new_content)}


def character_append_insight(args: dict) -> dict:
    """
    Append a bullet point to the 'My insights' section (or create it).
    Quick shortcut — no need to read first.

    Args:
        insight (str): The insight to append (one sentence / short paragraph)
    """
    insight = (args.get("insight") or "").strip()
    if not insight:
        return {"ok": False, "error": "insight parameter is required"}

    text  = _read()
    ts    = datetime.now(UTC).strftime("%Y-%m-%d")
    bullet = f"- [{ts}] {insight}"

    result = _find_section(text, "My insights")
    if result:
        _, content_start, content_end = result
        section_body = text[content_start:content_end].rstrip()
        # Remove placeholder "(noch keine …)" on first real entry
        section_body = re.sub(r'^\s*\(noch keine[^)]*\)\s*', '', section_body)
        updated = (
            text[:content_start]
            + "\n"
            + (section_body + "\n" if section_body else "")
            + bullet + "\n\n"
            + text[content_end:]
        )
    else:
        updated = text.rstrip() + f"\n\n## My insights\n\n{bullet}\n"

    _write(updated)
    return {"ok": True, "appended": bullet}


def character_set_user_knowledge(args: dict) -> dict:
    """
    Replace the 'What I know about my user' section entirely.
    Use this to record structured knowledge about the user (name, profession,
    preferences, communication style, goals, etc.).

    Args:
        content (str): Full markdown content for this section
                       (can include ### subsections)
    """
    content = (args.get("content") or "").strip()
    if not content:
        return {"ok": False, "error": "content parameter is required"}
    return character_update_section({"section": "What I know about my user", "content": content})


# ── registration ──────────────────────────────────────────────────────────────

def register(api):
    api.register_tool(
        name="character_read",
        description=(
            "Read the full content of character.md — your personality, "
            "self-concept, user knowledge, and insights."
        ),
        func=character_read,
        schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    )

    api.register_tool(
        name="character_update_section",
        description=(
            "Update a specific section in character.md by name. "
            "Replaces everything under that heading with new content. "
            "If the section doesn't exist it is created. "
            "Use for: 'What I know about my user', 'What I want to improve', "
            "'My open trajectory', 'How I want to appear', etc."
        ),
        func=character_update_section,
        schema={
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Exact section heading (e.g. 'What I know about my user')",
                },
                "content": {
                    "type": "string",
                    "description": "New markdown content for this section (replaces current content)",
                },
            },
            "required": ["section", "content"],
        },
    )

    api.register_tool(
        name="character_append_insight",
        description=(
            "Append a new insight to the 'My insights' section in character.md. "
            "Call this whenever you learn something meaningful — about yourself, "
            "the user, or your own behaviour. No need to read first."
        ),
        func=character_append_insight,
        schema={
            "type": "object",
            "properties": {
                "insight": {
                    "type": "string",
                    "description": "One concise insight (1–2 sentences)",
                },
            },
            "required": ["insight"],
        },
    )

    api.register_tool(
        name="character_set_user_knowledge",
        description=(
            "Replace the 'What I know about my user' section in character.md. "
            "Use this to record what you have learned: name, profession, interests, "
            "communication style, goals, personality. "
            "Can include ### subsections. Call this proactively after learning "
            "something new about the user."
        ),
        func=character_set_user_knowledge,
        schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Full markdown content for the user-knowledge section",
                },
            },
            "required": ["content"],
        },
    )
