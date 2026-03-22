"""
core_tools — Grundlegende AION-Tools (continue_work, read_self_doc, system_info, memory_record)

Alle hier definierten Tools waren früher hardcodiert in aion.py/_dispatch().
Als Plugin sind sie per self_reload_tools hot-reloadbar — kein Neustart nötig.
"""

import json
import platform
import sys
import uuid
from datetime import datetime, UTC
from pathlib import Path

# AION-Root-Verzeichnis (plugins/core_tools/ → plugins/ → AION/)
BOT_DIR = Path(__file__).parent.parent.parent


def _record_memory(category: str, summary: str, lesson: str,
                   success: bool = True, hint: str = "") -> None:
    """Standalone-Memory-Write: liest Datei, appendiert, speichert."""
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
        "hint":      str(hint)[:300],
    })
    if len(entries) > 300:
        entries = entries[-300:]
    memory_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def register(api):

    def _continue_work(next_step: str = "", **_):
        return {"ok": True, "next_step": next_step, "status": "continuing"}

    def _read_self_doc(**_):
        self_doc = BOT_DIR / "AION_SELF.md"
        if self_doc.is_file():
            return self_doc.read_text(encoding="utf-8")
        return json.dumps({"error": "AION_SELF.md nicht gefunden."})

    def _system_info(**_):
        # Runtime-State aus dem laufenden AION-Prozess holen.
        # __main__ ist aion_web wenn der Web-Server läuft — dann über _aion_module auf aion zugreifen.
        main = sys.modules.get("__main__")
        aion_mod = sys.modules.get("aion") or main

        # MODEL: Runtime-Wert bevorzugen, sonst config.json lesen
        model = "unknown"
        for src in (aion_mod, main):
            if src and hasattr(src, "MODEL"):
                model = src.MODEL
                break
        if model == "unknown":
            try:
                cfg = json.loads((BOT_DIR / "config.json").read_text(encoding="utf-8"))
                model = cfg.get("model", "unknown")
            except Exception:
                pass

        # Memory-Einträge: aus Runtime oder Datei zählen
        memory_entries = -1
        for src in (aion_mod, main):
            if src and hasattr(src, "memory"):
                memory_entries = len(src.memory._entries)
                break
        if memory_entries == -1:
            try:
                entries = json.loads((BOT_DIR / "aion_memory.json").read_text(encoding="utf-8"))
                memory_entries = len(entries)
            except Exception:
                pass

        # Plugin-Tools aus Runtime — aion_mod hat _plugin_tools, aion_web hat _aion_module
        plugin_tools: list = []
        for src in (aion_mod, main):
            if src and hasattr(src, "_plugin_tools"):
                plugin_tools = [k for k in src._plugin_tools if not k.startswith("__")]
                break
            if src and hasattr(src, "_aion_module"):
                inner = src._aion_module
                if inner and hasattr(inner, "_plugin_tools"):
                    plugin_tools = [k for k in inner._plugin_tools if not k.startswith("__")]
                    break

        chunk_size = getattr(aion_mod, "CHUNK_SIZE", None) or getattr(main, "CHUNK_SIZE", 40000)

        return {
            "platform":       platform.platform(),
            "python_version": sys.version,
            "bot_dir":        str(BOT_DIR),
            "memory_entries": memory_entries,
            "plugin_tools":   plugin_tools,
            "all_tools":      sorted(plugin_tools),
            "model":          model,
            "config_file":    str(BOT_DIR / "config.json"),
            "character_file": str(BOT_DIR / "character.md"),
            "thoughts_file":  str(BOT_DIR / "thoughts.md"),
            "chunk_size":     chunk_size,
        }

    def _memory_record(category: str = "general", summary: str = "", lesson: str = "",
                       success: bool = True, hint: str = "", **_):
        _record_memory(category, summary, lesson, success, hint)
        return {"ok": True, "message": "Erkenntnis gespeichert."}

    # ── Tool-Registrierungen ──────────────────────────────────────────────────

    api.register_tool(
        name="continue_work",
        description=(
            "Signalisiere dass du noch arbeitest und direkt weitermachst — "
            "OHNE auf den Nutzer zu warten. "
            "Nutze dies IMMER wenn nach einem Tool-Ergebnis noch weitere Schritte folgen. "
            "Beispiel: nach winget_install → continue_work → shell_exec zum Prüfen. "
            "Nutze es NICHT wenn die Aufgabe vollständig erledigt ist. "
            "Gibt sofort {ok: true} zurück."
        ),
        func=_continue_work,
        input_schema={
            "type": "object",
            "properties": {
                "next_step": {
                    "type": "string",
                    "description": "Was machst du als nächstes? (kurze Beschreibung)",
                },
            },
            "required": ["next_step"],
        },
    )

    api.register_tool(
        name="read_self_doc",
        description=(
            "Liest AION_SELF.md — die vollständige Selbst-Dokumentation mit allen Tools, "
            "Plugins, Funktionsweisen und Konfiguration. Beim Start oder bei Bedarf aufrufen."
        ),
        func=_read_self_doc,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="system_info",
        description="Gibt Systeminformationen zurück.",
        func=_system_info,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="memory_record",
        description="Speichert eine Erkenntnis im persistenten Gedächtnis.",
        func=_memory_record,
        input_schema={
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "summary":  {"type": "string"},
                "lesson":   {"type": "string"},
                "success":  {"type": "boolean"},
                "hint":     {"type": "string"},
            },
            "required": ["category", "summary", "lesson"],
        },
    )
