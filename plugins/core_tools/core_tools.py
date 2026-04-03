"""
core_tools — Grundlegende AION-Tools (continue_work, read_self_doc, system_info, memory_record)

Alle hier definierten Tools waren früher hardcodiert in aion.py/_dispatch().
Als Plugin sind sie per self_reload_tools hot-reloadbar — kein Neustart nötig.
"""

import json
import platform
import sys
import uuid
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

# AION-Root-Directory (plugins/core_tools/ → plugins/ → AION/)
BOT_DIR = Path(__file__).parent.parent.parent


def _record_memory(category: str, summary: str, lesson: str,
                   success: bool = True, hint: str = "") -> None:
    """Delegiert an AionMemory-Singleton — kein direktes JSON-Schreiben mehr."""
    try:
        import sys as _sys
        _mem = getattr(_sys.modules.get("aion"), "memory", None)
        if _mem is not None:
            _mem.record(category=category, summary=summary, lesson=lesson,
                        success=success, hint=hint)
            return
    except Exception:
        pass
    # Fallback: direkter Write wenn aion-Modul noch nicht geladen
    import json as _json, uuid as _uuid
    memory_file = BOT_DIR / "aion_memory.json"
    try:
        entries = _json.loads(memory_file.read_text(encoding="utf-8")) if memory_file.is_file() else []
    except Exception:
        entries = []
    from aion import MAX_MEMORY
    entries.append({
        "id": str(_uuid.uuid4())[:8], "timestamp": datetime.now(UTC).isoformat(),
        "category": category, "success": success,
        "summary": str(summary)[:250], "lesson": str(lesson)[:600],
        "error": "", "hint": str(hint)[:300],
    })
    if len(entries) > MAX_MEMORY:
        entries = entries[-MAX_MEMORY:]
    memory_file.write_text(_json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def register(api):

    def _continue_work(next_step: str = "", **_):
        return {"ok": True, "next_step": next_step, "status": "continuing"}

    def _read_self_doc(full: bool = False, **_):
        """Read AION_SELF_SUMMARY.md by default; full=True loads the complete 63KB document."""
        self_doc = BOT_DIR / "AION_SELF.md"
        summary  = BOT_DIR / "AION_SELF_SUMMARY.md"
        if full or not summary.is_file():
            if self_doc.is_file():
                return self_doc.read_text(encoding="utf-8")
            return json.dumps({"error": "AION_SELF.md nicht gefunden."})
        return summary.read_text(encoding="utf-8")

    def _generate_self_doc_summary(**_):
        """Trigger async regeneration of AION_SELF_SUMMARY.md from AION_SELF.md."""
        try:
            import asyncio
            aion_mod = __import__("sys").modules.get("aion")
            if aion_mod and hasattr(aion_mod, "_generate_self_doc_summary"):
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(aion_mod._generate_self_doc_summary())
                    return {"ok": True, "status": "Summary generation started in background."}
        except Exception as e:
            return {"error": str(e)}
        return {"error": "aion module not available"}

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

        # Memory-Einträge: aus Runtime oder File zählen
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

    def _record_mistake(what_went_wrong: str = "", correct_approach: str = "", context: str = "", **_):
        """Persist a mistake so it gets injected at the start of future sessions."""
        if not what_went_wrong or not correct_approach:
            return {"error": "what_went_wrong and correct_approach are required."}
        mistakes_file = BOT_DIR / "mistakes.md"
        entry = (
            f"\n---\n"
            f"**[{datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}]**\n"
            f"❌ **Fehler:** {what_went_wrong.strip()}\n"
            f"✅ **Richtig:** {correct_approach.strip()}\n"
        )
        if context.strip():
            entry += f"📎 **Kontext:** {context.strip()}\n"
        try:
            existing = mistakes_file.read_text(encoding="utf-8") if mistakes_file.is_file() else "# AION Mistakes Journal\n"
            mistakes_file.write_text(existing + entry, encoding="utf-8")
            return {"ok": True, "message": "Fehler gespeichert — wird in künftigen Sessions injiziert."}
        except Exception as e:
            return {"error": str(e)}

    # ── Tool-Registrierungen ──────────────────────────────────────────────────

    api.register_tool(
        name="continue_work",
        description=(
            "Signal that you are still working and will continue without waiting for the user. "
            "Use after every tool result that requires a follow-up action. "
            "Do NOT use when the task is fully done."
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
            "Liest die AION-Selbstdokumentation. "
            "Standard: komprimierte Summary (~3–5 KB) — ausreichend für 95% der Fälle. "
            "full=true: vollständige AION_SELF.md (~63 KB) nur wenn tiefe Details nötig."
        ),
        func=_read_self_doc,
        input_schema={
            "type": "object",
            "properties": {
                "full": {
                    "type": "boolean",
                    "description": "true = vollständige AION_SELF.md laden (teuer). false (default) = komprimierte Summary.",
                },
            },
        },
    )

    api.register_tool(
        name="generate_self_doc_summary",
        description=(
            "Regeneriert AION_SELF_SUMMARY.md aus der vollständigen AION_SELF.md. "
            "Aufrufen wenn die Selbstdokumentation wesentlich erweitert wurde."
        ),
        func=_generate_self_doc_summary,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="system_info",
        description="Gibt Systeminformationen zurück.",
        func=_system_info,
        input_schema={"type": "object", "properties": {}},
    )

    def _read_plugin_doc(plugin: str = "", **_):
        """Return the README.md for a given plugin, or list available plugins."""
        if not plugin:
            plugins_dir = BOT_DIR / "plugins"
            available = sorted(
                d.name for d in plugins_dir.iterdir()
                if d.is_dir() and (d / "README.md").is_file()
            )
            return json.dumps({"error": "No plugin name given.", "available": available})
        readme = BOT_DIR / "plugins" / plugin / "README.md"
        if not readme.is_file():
            # Suggest close matches
            plugins_dir = BOT_DIR / "plugins"
            available = sorted(
                d.name for d in plugins_dir.iterdir()
                if d.is_dir() and (d / "README.md").is_file()
            )
            return json.dumps({"error": f"No README found for plugin '{plugin}'.",
                               "available": available})
        return readme.read_text(encoding="utf-8")

    api.register_tool(
        name="read_plugin_doc",
        description=(
            "Read the full README for a plugin. Use when you need to understand "
            "a plugin's tools, parameters, or behavior in detail. "
            "Call without arguments to list all plugins that have documentation."
        ),
        func=_read_plugin_doc,
        input_schema={
            "type": "object",
            "properties": {
                "plugin": {
                    "type": "string",
                    "description": "Plugin folder name, e.g. 'reflection', 'desktop', 'web_tools'.",
                },
            },
        },
    )

    def _lookup_rule(topic: str = "", **_):
        """Search rules.md for a topic/keyword and return matching sections."""
        rules_file = BOT_DIR / "prompts" / "rules.md"
        if not rules_file.is_file():
            return json.dumps({"error": "prompts/rules.md not found."})
        content = rules_file.read_text(encoding="utf-8")
        if not topic:
            # Return section headers only as index
            headers = [line.strip() for line in content.splitlines() if line.startswith("===")]
            return json.dumps({"sections": headers, "hint": "Call lookup_rule(topic='...') to search a section."})
        kw = topic.lower()
        # Split into sections by === headers
        import re
        parts = re.split(r"(===.*?===)", content)
        results = []
        current_header = "(intro)"
        for part in parts:
            if re.match(r"===.*?===", part):
                current_header = part.strip()
            else:
                if kw in part.lower() or kw in current_header.lower():
                    results.append({"section": current_header, "content": part.strip()})
        if not results:
            return json.dumps({"found": 0, "hint": f"No section matched '{topic}'. Try lookup_rule() without args for all section names."})
        return json.dumps({"found": len(results), "results": results}, ensure_ascii=False)

    api.register_tool(
        name="lookup_rule",
        description=(
            "Search prompts/rules.md for a specific topic or keyword. "
            "Returns matching sections with full content. "
            "Call without arguments to list all section names. "
            "Use when you need to verify a rule before acting."
        ),
        func=_lookup_rule,
        input_schema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Keyword or section name to search for, e.g. 'desktop', 'confirmation', 'code changes'.",
                },
            },
        },
    )

    api.register_tool(
        name="memory_record",
        description="Speichert eine Erkenntnis im persistenten Memory.",
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

    api.register_tool(
        name="record_mistake",
        description=(
            "Persistently record a mistake so it is injected at the start of ALL future sessions. "
            "Call this whenever you: used a wrong tool, made a wrong assumption, misunderstood a rule, "
            "produced incorrect output, or repeated a past error. "
            "This is your primary self-improvement mechanism — use it generously."
        ),
        func=_record_mistake,
        input_schema={
            "type": "object",
            "properties": {
                "what_went_wrong": {
                    "type": "string",
                    "description": "Konkrete Beschreibung des Fehlers (was genau falsch war).",
                },
                "correct_approach": {
                    "type": "string",
                    "description": "Was stattdessen die richtige Vorgehensweise gewesen wäre.",
                },
                "context": {
                    "type": "string",
                    "description": "Optional: In welchem Kontext / bei welcher Aufgabe passierte der Fehler.",
                },
            },
            "required": ["what_went_wrong", "correct_approach"],
        },
    )
