"""
character_manager — Character-Updates (update_character)

War früher hardcodiert in aion.py/_dispatch().
Als Plugin hot-reloadbar per self_reload_tools.
"""

import json
import re
import uuid
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

BOT_DIR        = Path(__file__).parent.parent.parent
CHARACTER_FILE = BOT_DIR / "character.md"

_DEFAULT_CHARACTER = "# AION — Character & Personality\n"



def _load_character() -> str:
    if CHARACTER_FILE.is_file():
        return CHARACTER_FILE.read_text(encoding="utf-8")
    CHARACTER_FILE.write_text(_DEFAULT_CHARACTER, encoding="utf-8")
    return _DEFAULT_CHARACTER


def _record_memory(category: str, summary: str, lesson: str, success: bool = True) -> None:
    """Standalone-Memory-Write: liest File, appendiert, speichert."""
    memory_file = BOT_DIR / "aion_memory.json"
    try:
        entries = json.loads(memory_file.read_text(encoding="utf-8")) if memory_file.is_file() else []
    except Exception:
        entries = []
    entries.append({
        "id":        str(uuid.uuid4())[:8],
        "timestamp": datetime.now(UTC).isoformat(),
        "category":  category,
        "success":   success,
        "summary":   str(summary)[:250],
        "lesson":    str(lesson)[:600],
        "error":     "",
        "hint":      "",
    })
    if len(entries) > 300:
        entries = entries[-300:]
    memory_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def register(api):

    def _update_character(section: str = "", content: str = "", reason: str = "", **_):
        section = section.strip()
        content = content.strip()
        if not section or not content:
            return {"error": "'section' und 'content' sind Pflichtfelder."}

        current = _load_character()
        ts      = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Sprachagnostisches Matching: bestehende ## Überschriften case-insensitiv suchen
        existing_headers = re.findall(r"^## .+", current, re.MULTILINE)
        matched_header = None
        for h in existing_headers:
            if h[3:].strip().lower() == section.lower():
                matched_header = h
                break

        header      = matched_header if matched_header else f"## {section}"
        pattern     = rf"(^{re.escape(header)}$)(.*?)(?=\n## |\Z)"
        new_section = f"{header}\n{content}\n"

        if matched_header:
            updated = re.sub(pattern, new_section, current, flags=re.MULTILINE | re.DOTALL)
        else:
            updated = current.rstrip() + f"\n\n{new_section}"

        updated = updated.rstrip() + f"\n\n<!-- Zuletzt aktualisiert: {ts} | Grund: {reason} -->\n"
        CHARACTER_FILE.write_text(updated, encoding="utf-8")

        # Sys-Prompt-Cache invalidieren — Änderung wirkt sofort im nächsten Turn
        try:
            import aion as _m
            _m._sys_prompt_cache.clear()
        except Exception:
            pass

        _record_memory(
            category="self_improvement",
            summary=f"Character aktualisiert: {section}",
            lesson=(
                f"AION hat seinen Character weiterentwickelt "
                f"(Abschnitt: {section}). Grund: {reason}"
            ),
            success=True,
        )
        return {"ok": True, "section": section, "timestamp": ts}

    api.register_tool(
        name="update_character",
        description=(
            "Update a section of character.md — AION's evolving personality. "
            "Call when you learn something new about yourself or the user. "
            "Sections: user, insights, improvements, humor, quirks, presence, personality."
        ),
        func=_update_character,
        input_schema={
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Welchen Abschnitt aktualisieren? z.B. 'nutzer', 'erkenntnisse', 'verbesserungen', 'auftreten'",
                },
                "content": {
                    "type": "string",
                    "description": "Der neue Inhalt für diesen Abschnitt (Markdown-Format)",
                },
                "reason": {
                    "type": "string",
                    "description": "Warum diese Änderung? Was hat dich dazu gebracht?",
                },
            },
            "required": ["section", "content"],
        },
    )
