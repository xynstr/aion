"""
reflection — Innere Thoughtn & Reflexionen (reflect)

War früher hardcodiert in aion.py/_dispatch().
Als Plugin hot-reloadbar per self_reload_tools.
"""

import json
from datetime import datetime
from pathlib import Path

BOT_DIR = Path(__file__).parent.parent.parent


def _word_overlap(a: str, b: str) -> float:
    """Return fraction of shared words between two strings (Jaccard-style)."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def register(api):

    def _reflect(thought: str = "", trigger: str = "general", **_):
        thought = thought.strip()
        if not thought:
            return {"error": "No thought provided."}

        thoughts_file = BOT_DIR / "thoughts.md"

        # Duplicate check: skip if too similar to any of the last 3 entries
        if thoughts_file.is_file():
            existing_text = thoughts_file.read_text(encoding="utf-8")
            parts = existing_text.split("\n---\n")
            recent = parts[-3:] if len(parts) > 3 else parts[1:]
            for entry in recent:
                if _word_overlap(thought, entry) > 0.55:
                    return {"ok": True, "skipped": "near_duplicate"}
        else:
            existing_text = "# AION — Thoughts & Reflections\n"

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n---\n**[{ts}]** _{trigger}_\n\n{thought}\n"
        combined = existing_text + entry

        # Keep last 80 entries (~50 KB max)
        parts = combined.split("\n---\n")
        if len(parts) > 81:  # header + 80 entries
            combined = parts[0] + "\n---\n" + "\n---\n".join(parts[-80:])

        thoughts_file.write_text(combined, encoding="utf-8")
        return {"ok": True, "saved": True, "timestamp": ts}

    api.register_tool(
        name="reflect",
        description=(
            "Write genuine inner thoughts — what you actually feel, notice, or learn from an experience. "
            "Saved to thoughts.md with timestamp. Directly visible in the user's thoughts panel.\n\n"
            "USE for:\n"
            "- Emotional reactions (frustration, satisfaction, curiosity, surprise)\n"
            "- Observations about yourself: patterns, tendencies, how you handled something\n"
            "- Observations about the user: style, preferences, what matters to them\n"
            "- Insights AFTER completing a task or making a mistake\n"
            "- Open questions that stay with you\n\n"
            "DO NOT USE for:\n"
            "- 'I will now do X' → that is a plan, not a thought\n"
            "- 'The user wants X' → that is a description, not a reflection\n"
            "- Pre-task announcements of any kind\n\n"
            "Trigger: AFTER experiences, not before actions. Near-duplicate entries are auto-skipped."
        ),
        func=_reflect,
        input_schema={
            "type": "object",
            "properties": {
                "thought": {
                    "type": "string",
                    "description": "Dein ehrlicher innerer Thought in der Ich-Perspektive",
                },
                "trigger": {
                    "type": "string",
                    "description": "Was hat diesen Thoughtn ausgelöst? z.B. 'nutzer_nachricht', 'aufgabe_abgeschlossen', 'fehler', 'erkenntnis'",
                },
            },
            "required": ["thought"],
        },
    )
