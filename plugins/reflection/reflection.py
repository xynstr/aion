"""
reflection — Innere Gedanken & Reflexionen (reflect)

War früher hardcodiert in aion.py/_dispatch().
Als Plugin hot-reloadbar per self_reload_tools.
"""

import json
from datetime import datetime
from pathlib import Path

BOT_DIR = Path(__file__).parent.parent.parent


def register(api):

    def _reflect(thought: str = "", trigger: str = "allgemein", **_):
        thought = thought.strip()
        if not thought:
            return {"error": "Kein Gedanke angegeben."}

        thoughts_file = BOT_DIR / "thoughts.md"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n---\n**[{ts}]** _{trigger}_\n\n{thought}\n"

        existing = (
            thoughts_file.read_text(encoding="utf-8")
            if thoughts_file.is_file()
            else "# AION — Gedanken & Reflexionen\n"
        )
        combined = existing + entry

        # Auf letzte 80 Einträge kürzen (ca. 50 KB max)
        parts = combined.split("\n---\n")
        if len(parts) > 81:  # Header + 80 Einträge
            combined = parts[0] + "\n---\n" + "\n---\n".join(parts[-80:])

        thoughts_file.write_text(combined, encoding="utf-8")
        return {"ok": True, "saved": True, "timestamp": ts}

    api.register_tool(
        name="reflect",
        description=(
            "Schreibe echte innere Gedanken — was du denkst, planst, beobachtest oder lernst. "
            "Dies wird in einer thoughts.md Datei gespeichert mit Zeitstempel. "
            "Nutze dies IMMER nach jeder Nutzer-Nachricht und nach abgeschlossenen Aufgaben. "
            "Gedanken sollten konkret sein: Was will der Nutzer? Was plane ich? Was lerne ich?"
        ),
        func=_reflect,
        input_schema={
            "type": "object",
            "properties": {
                "thought": {
                    "type": "string",
                    "description": "Dein ehrlicher innerer Gedanke in der Ich-Perspektive",
                },
                "trigger": {
                    "type": "string",
                    "description": "Was hat diesen Gedanken ausgelöst? z.B. 'nutzer_nachricht', 'aufgabe_abgeschlossen', 'fehler', 'erkenntnis'",
                },
            },
            "required": ["thought"],
        },
    )
