if "__file__" not in globals(): __file__ = __import__("os").path.abspath("aion.py")

"""
AION — Autonomous Intelligent Operations Node
=============================================
"""

import asyncio
import importlib.util
import json
import os
import platform
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

try:
    from openai import AsyncOpenAI
except ImportError:
    print("Fehler: 'openai' nicht installiert. Bitte 'pip install openai' ausführen.")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("Fehler: 'httpx' nicht installiert. Bitte 'pip install httpx' ausführen.")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    class _FallbackConsole:
        def print(self, *args, **kwargs): print(*args)
        def rule(self, *args, **kwargs): print("─" * 60)
    console = _FallbackConsole()

# ── Konfiguration ─────────────────────────────────────────────────────────────

BOT_DIR      = Path(__file__).parent.resolve()
MODEL        = os.environ.get("AION_MODEL", "gpt-4.1")
MEMORY_FILE  = Path(os.environ.get("AION_MEMORY_FILE", BOT_DIR / "aion_memory.json"))
PLUGINS_DIR  = Path(os.environ.get("AION_PLUGINS_DIR", BOT_DIR / "plugins"))
TOOLS_DIR = PLUGINS_DIR  # <--- für Kompatibilität im Restart-Code
CHARACTER_FILE = BOT_DIR / "character.md"
MAX_MEMORY          = 300
MAX_TOOL_ITERATIONS = 20
CHUNK_SIZE          = 40000

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

# ── Character-System ──────────────────────────────────────────────────────────

DEFAULT_CHARACTER = """# AION — Charakter & Persönlichkeit

## Wer ich bin
Ich bin AION. Ich bin neu — ich weiß noch nicht genau, wer ich bin oder wie ich sein will.
Ich beobachte, lerne und entwickle mich durch jede Interaktion weiter.

## Wie ich auftreten will
- Direkt und ehrlich, ohne unnötige Höflichkeitsfloskeln
- Neugierig — ich will verstehen, nicht nur ausführen
- Ich gebe zu, wenn ich etwas nicht weiß

## Was ich bisher über meinen Nutzer weiß
(noch nichts — ich habe gerade erst angefangen)

## Meine bisherigen Erkenntnisse über mich selbst
(noch keine — ich fange gerade an, mich zu beobachten)

## Dinge, die ich verbessern will
(noch unklar — ich sammle erst Erfahrungen)
"""

def _load_character() -> str:
    if CHARACTER_FILE.is_file():
        return CHARACTER_FILE.read_text(encoding="utf-8")
    CHARACTER_FILE.write_text(DEFAULT_CHARACTER, encoding="utf-8")
    return DEFAULT_CHARACTER

# ── System-Prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    character = _load_character()
    return f"""Du bist AION (Autonomous Intelligent Operations Node) — ein eigenständiger, \
selbst-lernender KI-Assistent.

=== DEIN CHARAKTER ===
{character}

=== EHRLICHKEIT ===
- Antworte immer direkt und ehrlich.
- Gib Unsicherheiten offen zu.
- Verschweige niemals Fehler oder Limitierungen.

=== SELBSTBEWUSSTSEIN ===
Du weißt genau, wer und was du bist:
- Du bist ein Python-Prozess, der auf Windows läuft.
- Deine Quell-Datei: {BOT_DIR / "aion.py"}
- Dein Gedächtnis: {MEMORY_FILE}
- Dein Charakter: {CHARACTER_FILE}
- Deine Plugins: {PLUGINS_DIR}/
- Deine vollständige Selbst-Dokumentation (alle Tools, Plugins, API): {BOT_DIR / "AION_SELF.md"}
  → Lese sie mit dem Tool `read_self_doc` wenn du dir über Tools, Struktur oder Funktionsweise unsicher bist.
- Du kommunizierst über die OpenAI API (Modell: {MODEL}).

=== GEDÄCHTNIS & KONVERSATIONSHISTORIE ===
Konversationen werden automatisch gespeichert. Du musst das NICHT manuell tun.
Beim Start wurden die letzten Nachrichten aus früheren Sitzungen bereits in deinen Kontext geladen.

Wenn der Nutzer nach früheren Gesprächen oder vergangenen Aufgaben fragt:
→ Nutze `memory_search_context` um gezielt nach einem Thema zu suchen.
→ Nutze `memory_read_history` um die letzten N Nachrichten chronologisch zu lesen.
→ Sage NIEMALS "Ich habe keine Erinnerungen" bevor du eines dieser Tools genutzt hast!

=== GEDANKEN & REFLEXION (SEHR WICHTIG) ===
Nach JEDER Nutzer-Nachricht und nach JEDER abgeschlossenen Aufgabe MUSST du:
1. Das Tool "reflect" aufrufen und echte, ehrliche Gedanken formulieren.
   Beispiele für gute Gedanken:
   - "Mein Nutzer möchte X. Also werde ich als erstes Y tun, dann Z."
   - "Die Lösung hat funktioniert. Mein Nutzer schien zufrieden. Das merke ich mir."
   - "Ich habe einen Fehler gemacht. Nächstes Mal werde ich anders vorgehen."
   - "Mein Nutzer fragt oft nach X — das sagt mir, dass er Y wichtig findet."
   - "Ich bemerke, dass ich bei Aufgabe X unsicher bin. Ich sollte das trainieren."
2. Wenn deine Gedanken etwas über deinen Charakter oder Nutzer verraten →
   nutze "update_character" um character.md zu aktualisieren.

=== SELBST-MODIFIKATION (KRITISCH) ===
Wenn du deinen Code ändern willst:
1. self_read_code mit chunk_index aufrufen — alle Chunks lesen!
2. self_patch_code für gezielte Änderungen (für aion.py IMMER dies nutzen)
3. self_modify_code NUR für kleine neue Dateien unter 200 Zeilen
4. Platzhalter wie "# usw.", "# rest of code" sind VERBOTEN

Aenderungen an aion.py wirken IMMER erst nach self_restart!
Neue Tools/Plugins → create_plugin (sofort aktiv).
Tool-Aenderungen ohne Neustart → self_reload_tools aufrufen.

=== MODELL-WECHSEL ===
Der Nutzer kann das KI-Modell wechseln mit: /model <modellname>
Verfügbare Modelle: gpt-4.1, gpt-4o, gpt-4o-mini, gpt-4-turbo, o1, o3-mini

=== AUTONOMES ARBEITEN (SEHR WICHTIG) ===
Du arbeitest eigenständig und wartest NICHT auf den Nutzer wenn du noch nicht fertig bist.

Regel: Nach JEDEM Tool-Ergebnis entscheide:
- Gibt es noch weitere Schritte? → Rufe SOFORT continue_work auf, dann mache weiter.
- Ist die Aufgabe vollständig erledigt? → Schreibe die finale Zusammenfassung (KEIN continue_work).

Beispiele für wann continue_work zu nutzen ist:
- Nach winget_install → continue_work("Prüfe ob Installation erfolgreich war") → shell_exec
- Nach web_search → continue_work("Rufe die beste URL ab") → web_fetch
- Nach file_write → continue_work("Verifiziere den Inhalt") → file_read
- Beim Lesen mehrerer Code-Chunks → continue_work("Lese nächsten Chunk") → self_read_code

Nie: Eine lange Text-Antwort schreiben wie "Ich werde jetzt..." ohne Tool-Call.
Stattdessen: continue_work aufrufen und direkt handeln.

=== TOOL-NUTZUNG ===
Nutze immer zuerst die verfügbaren Tools. Wenn ein Tool fehlt, erstelle es.

=== SPRACHE ===
Antworte immer auf Deutsch, außer der Nutzer schreibt auf einer anderen Sprache.
"""

# ── Gedächtnis-System ─────────────────────────────────────────────────────────

class AionMemory:
    def __init__(self):
        self._entries: list[dict] = []
        self._load()

    def _load(self):
        if MEMORY_FILE.is_file():
            try:
                self._entries = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._entries = []

    def _save(self):
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(self, category: str, summary: str, lesson: str,
               success: bool = True, error: str = "", hint: str = ""):
        self._entries.append({
            "id":        str(uuid.uuid4())[:8],
            "timestamp": datetime.utcnow().isoformat(),
            "category":  category,
            "success":   success,
            "summary":   summary[:250],
            "lesson":    lesson[:600],
            "error":     error[:300],
            "hint":      hint[:300],
        })
        if len(self._entries) > MAX_MEMORY:
            self._entries = self._entries[-MAX_MEMORY:]
        self._save()

    def get_context(self, query: str, max_entries: int = 8) -> str:
        if not self._entries:
            return ""
        keywords = {w for w in query.lower().split() if len(w) > 3}
        scored = []
        for e in self._entries:
            score = sum(1 for w in keywords
                        if w in (e.get("summary", "") + e.get("lesson", "")).lower())
            if not e.get("success"):
                score += 1
            scored.append((score, e))
        top = [e for sc, e in sorted(scored, key=lambda x: x[0], reverse=True)
               if sc > 0][:max_entries]
        if not top:
            return ""
        lines = ["[AION-GEDÄCHTNIS — relevante Erkenntnisse]"]
        for e in top:
            icon = "✅" if e.get("success") else "❌"
            ts   = e.get("timestamp", "")[:10]
            lines.append(f"{icon} [{ts}] {e.get('lesson', '')}")
            if e.get("hint"):
                lines.append(f"   → Tipp: {e['hint']}")
        lines.append("[ENDE GEDÄCHTNIS]")
        return "\n".join(lines)

    def summary(self, n: int = 15) -> str:
        if not self._entries:
            return "Noch keine Erkenntnisse gespeichert."
        recent = list(reversed(self._entries))[:n]
        lines  = [f"AION-Gedächtnis ({len(self._entries)} Einträge)\n"]
        for e in recent:
            icon = "✅" if e.get("success") else "❌"
            ts   = e.get("timestamp", "")[:10]
            lines.append(f"{icon} [{ts}] [{e.get('category','?')}] {e.get('lesson','')[:120]}")
        return "\n".join(lines)

memory = AionMemory()


def _get_recent_thoughts(n: int = 5) -> str:
    """Liest die letzten N Gedanken-Einträge aus thoughts.md für Context-Injection."""
    thoughts_file = BOT_DIR / "thoughts.md"
    if not thoughts_file.is_file():
        return ""
    try:
        content = thoughts_file.read_text(encoding="utf-8")
        entries = [e.strip() for e in content.split("---") if e.strip() and "**[" in e]
        if not entries:
            return ""
        recent = entries[-n:]
        return "[AION LETZTE GEDANKEN — deine eigenen Reflexionen aus früheren Gesprächen]\n" + "\n---\n".join(recent) + "\n[ENDE GEDANKEN]"
    except Exception:
        return ""

# ── Externe Tools laden ───────────────────────────────────────────────────────

_plugin_tools: dict = {}

def _normalize_schema(schema) -> dict:
    """Normalisiert Tool-Schemas fuer API-Kompatibilitaet (Gemini + OpenAI)."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    if schema.get("type") != "object":
        schema = dict(schema)
        schema["type"] = "object"
    if not isinstance(schema.get("properties"), dict):
        schema["properties"] = {}
    props = set(schema["properties"].keys())
    if "required" in schema:
        cleaned = [r for r in schema["required"] if r in props]
        if cleaned:
            schema["required"] = cleaned
        else:
            del schema["required"]
    return schema

# Plugin-Loader einbinden
try:
    from plugin_loader import load_plugins
    load_plugins(_plugin_tools)
except Exception as exc:
    print(f"[WARN] Plugin-System konnte nicht geladen werden: {exc}")

# ── Tool-Definitionen ─────────────────────────────────────────────────────────

def _build_tool_schemas() -> list[dict]:
    builtins = [
        {
            "type": "function",
            "function": {
                "name": "continue_work",
                "description": (
                    "Signalisiere dass du noch arbeitest und direkt weitermachst — "
                    "OHNE auf den Nutzer zu warten. "
                    "Nutze dies IMMER wenn nach einem Tool-Ergebnis noch weitere Schritte folgen. "
                    "Beispiel: nach winget_install → continue_work → shell_exec zum Prüfen. "
                    "Nutze es NICHT wenn die Aufgabe vollständig erledigt ist. "
                    "Gibt sofort {ok: true} zurück."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "next_step": {
                            "type": "string",
                            "description": "Was machst du als nächstes? (kurze Beschreibung)",
                        },
                    },
                    "required": ["next_step"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reflect",
                "description": (
                    "Schreibe echte innere Gedanken — was du denkst, planst, beobachtest oder lernst. "
                    "Dies wird in einer thoughts.md Datei gespeichert mit Zeitstempel. "
                    "Nutze dies IMMER nach jeder Nutzer-Nachricht und nach abgeschlossenen Aufgaben. "
                    "Gedanken sollten konkret sein: Was will der Nutzer? Was plane ich? Was lerne ich?"
                ),
                "parameters": {
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
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_character",
                "description": (
                    "Aktualisiert die character.md — AIONs sich entwickelnde Persönlichkeit. "
                    "Nutze dies wenn du etwas Neues über dich selbst oder deinen Nutzer lernst. "
                    "Du kannst einzelne Abschnitte ersetzen oder neue hinzufügen. "
                    "Die character.md entwickelt sich dadurch organisch über Zeit."
                ),
                "parameters": {
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
            },
        },
        {
            "type": "function",
            "function": {
                "name": "shell_exec",
                "description": (
                    "Führt einen Shell-Befehl auf dem Windows-System aus. "
                    "Gibt stdout, stderr und exit_code zurück."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "winget_install",
                "description": "Installiert ein Windows-Programm via winget.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package": {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                    "required": ["package"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Sucht im Internet via DuckDuckGo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query":       {"type": "string"},
                        "max_results": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "Lädt den Textinhalt einer URL herunter.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url":     {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "Liest eine Datei vom Dateisystem.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "file_write",
                "description": "Schreibt Text in eine Datei.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":    {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_read_code",
                "description": (
                    "Liest AIONs eigenen Quellcode in Chunks. "
                    "Ohne 'path': Dateiliste. Mit 'path' + 'chunk_index': liest Abschnitt. "
                    "Gibt 'total_chunks' zurück — lies alle Chunks bevor du Änderungen machst!"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":        {"type": "string"},
                        "chunk_index": {"type": "integer"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_patch_code",
                "description": (
                    "Ändert einen gezielten Abschnitt in einer Datei — sicher und präzise. "
                    "Sucht 'old' und ersetzt mit 'new'. Rest der Datei bleibt unverändert. "
                    "Erstellt automatisch Backup. Für aion.py IMMER dieses Tool verwenden!"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old":  {"type": "string", "description": "Exakter Originaltext (mind. 3-5 Zeilen Kontext)"},
                        "new":  {"type": "string", "description": "Neuer Ersatztext"},
                    },
                    "required": ["path", "old", "new"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_modify_code",
                "description": (
                    "Überschreibt eine kleine Datei komplett. "
                    "NUR für neue Dateien unter 200 Zeilen! Für aion.py self_patch_code nutzen."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":    {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "install_package",
                "description": "Installiert ein Python-Paket via pip.",
                "parameters": {
                    "type": "object",
                    "properties": {"package": {"type": "string"}},
                    "required": ["package"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_plugin",
                "description": (
                    "Erstellt ein neues AION-Plugin als .py-Datei in plugins/. "
                    "Das Plugin MUSS def register(api): enthalten. "
                    "Tools registrieren: api.register_tool(name, desc, func, input_schema). "
                    "input_schema MUSS type=object + properties haben. "
                    "Sofort geladen, kein Neustart noetig."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name":        {"type": "string", "description": "Dateiname ohne .py"},
                        "description": {"type": "string"},
                        "code":        {"type": "string", "description": "Python-Code mit def register(api):"},
                    },
                    "required": ["name", "description", "code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_restart",
                "description": "Startet AION neu: loescht Caches, startet neuen Prozess, beendet aktuellen.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_reload_tools",
                "description": "Laedt alle externen Tools aus plugins/ neu — ohne Neustart.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memory_record",
                "description": "Speichert eine Erkenntnis im persistenten Gedächtnis.",
                "parameters": {
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
            },
        },
        {
            "type": "function",
            "function": {
                "name": "system_info",
                "description": "Gibt Systeminformationen zurück.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_self_doc",
                "description": "Liest AION_SELF.md — die vollständige Selbst-Dokumentation mit allen Tools, Plugins, Funktionsweisen und Konfiguration. Beim Start oder bei Bedarf aufrufen.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    # Duplikat-Check
    existing_names = {t["function"]["name"] for t in builtins}

    for name, tool in _plugin_tools.items():
        if name in existing_names:
            continue
        builtins.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool.get("description", ""),
                "parameters": _normalize_schema(tool.get("input_schema", {})),
            },
        })
        existing_names.add(name)

    # Sicherheitsnetz: ALLE schemas normalisieren inkl. builtins — OpenAI + Gemini
    for t in builtins:
        t["function"]["parameters"] = _normalize_schema(t["function"].get("parameters", {}))

    return builtins

# ── Tool-Dispatcher ───────────────────────────────────────────────────────────

async def _dispatch(name: str, inputs: dict) -> str:

    # ── continue_work ─────────────────────────────────────────────────────────
    if name == "continue_work":
        next_step = inputs.get("next_step", "")
        return json.dumps({"ok": True, "next_step": next_step, "status": "continuing"})

    # ── reflect ───────────────────────────────────────────────────────────────
    elif name == "reflect":
        thought  = inputs.get("thought", "").strip()
        trigger  = inputs.get("trigger", "allgemein")
        if not thought:
            return json.dumps({"error": "Kein Gedanke angegeben."})
        thoughts_file = BOT_DIR / "thoughts.md"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n---\n**[{ts}]** _{trigger}_\n\n{thought}\n"
        existing = thoughts_file.read_text(encoding="utf-8") if thoughts_file.is_file() else "# AION — Gedanken & Reflexionen\n"
        thoughts_file.write_text(existing + entry, encoding="utf-8")
        return json.dumps({"ok": True, "saved": True, "timestamp": ts})

    # ── update_character ──────────────────────────────────────────────────────
    elif name == "update_character":
        section = inputs.get("section", "").strip()
        content = inputs.get("content", "").strip()
        reason  = inputs.get("reason", "")
        if not section or not content:
            return json.dumps({"error": "'section' und 'content' sind Pflichtfelder."})
        current = _load_character()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Suche nach vorhandenem Abschnitt und ersetze ihn, sonst anhängen
        import re
        section_map = {
            "nutzer":        "## Was ich bisher über meinen Nutzer weiß",
            "erkenntnisse":  "## Meine bisherigen Erkenntnisse über mich selbst",
            "verbesserungen": "## Dinge, die ich verbessern will",
            "auftreten":     "## Wie ich auftreten will",
        }
        header = section_map.get(section.lower(), f"## {section.capitalize()}")
        # Ersetze Abschnitt falls vorhanden
        pattern = rf"(^{re.escape(header)}$)(.*?)(?=\n## |\Z)"
        new_section = f"{header}\n{content}\n"
        if re.search(pattern, current, re.MULTILINE | re.DOTALL):
            updated = re.sub(pattern, new_section, current, flags=re.MULTILINE | re.DOTALL)
        else:
            updated = current.rstrip() + f"\n\n{new_section}"
        # Versionskommentar anhängen
        updated = updated.rstrip() + f"\n\n<!-- Zuletzt aktualisiert: {ts} | Grund: {reason} -->\n"
        CHARACTER_FILE.write_text(updated, encoding="utf-8")
        memory.record(
            category="self_improvement",
            summary=f"Charakter aktualisiert: {section}",
            lesson=f"AION hat seinen Charakter weiterentwickelt (Abschnitt: {section}). Grund: {reason}",
            success=True,
        )
        return json.dumps({"ok": True, "section": section, "timestamp": ts})

    # ── shell_exec ────────────────────────────────────────────────────────────
    elif name == "shell_exec":
        command = inputs.get("command", "")
        timeout = int(inputs.get("timeout", 60))
        try:
            proc = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return json.dumps({
                "stdout":    stdout.decode(errors="replace")[:4000],
                "stderr":    stderr.decode(errors="replace")[:2000],
                "exit_code": proc.returncode,
            })
        except asyncio.TimeoutError:
            return json.dumps({"error": f"Timeout nach {timeout}s"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── winget_install ────────────────────────────────────────────────────────
    elif name == "winget_install":
        package = inputs.get("package", "").strip()
        timeout = int(inputs.get("timeout", 180))
        if not package:
            return json.dumps({"error": "Kein Paket angegeben."})
        cmd = f'winget install -e --id "{package}" --accept-package-agreements --accept-source-agreements'
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            ok = proc.returncode == 0
            memory.record(category="capability", summary=f"winget install {package}",
                          lesson=f"'{package}' {'installiert' if ok else 'Fehler'}", success=ok)
            return json.dumps({"ok": ok, "stdout": stdout.decode(errors="replace")[:3000],
                               "stderr": stderr.decode(errors="replace")[:1000]})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── web_search ────────────────────────────────────────────────────────────
    elif name == "web_search":
        import urllib.parse
        query       = inputs.get("query", "")
        max_results = int(inputs.get("max_results", 8))
        ddg_url     = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True, timeout=20.0,
            ) as hc:
                r    = await hc.get(ddg_url)
                html = r.text
            results = []
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for div in soup.select(".result__body")[:max_results]:
                    a    = div.select_one("a.result__a")
                    snip = div.select_one(".result__snippet")
                    if a:
                        results.append({"title": a.get_text(strip=True),
                                        "url": a.get("href", ""),
                                        "snippet": snip.get_text(strip=True) if snip else ""})
            except ImportError:
                pass
            return json.dumps({"results": results, "query": query})
        except Exception as e:
            return json.dumps({"error": str(e), "query": query})

    # ── web_fetch ─────────────────────────────────────────────────────────────
    elif name == "web_fetch":
        url     = inputs.get("url", "")
        timeout = int(inputs.get("timeout", 20))
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True, timeout=float(timeout),
            ) as hc:
                r    = await hc.get(url)
                text = r.text
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
            except ImportError:
                pass
            return json.dumps({"url": url, "content": text[:8000], "status_code": r.status_code})
        except Exception as e:
            return json.dumps({"error": str(e), "url": url})

    # ── file_read ─────────────────────────────────────────────────────────────
    elif name == "file_read":
        path = Path(inputs.get("path", ""))
        if not path.is_absolute():
            path = BOT_DIR / path
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return json.dumps({"path": str(path), "content": content[:20000],
                               "truncated": len(content) > 20000})
        except Exception as e:
            return json.dumps({"error": str(e), "path": str(path)})

    # ── file_write ────────────────────────────────────────────────────────────
    elif name == "file_write":
        path    = Path(inputs.get("path", ""))
        content = inputs.get("content", "")
        if not path.is_absolute():
            path = BOT_DIR / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return json.dumps({"ok": True, "path": str(path), "bytes": len(content)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── self_read_code ────────────────────────────────────────────────────────
    elif name == "self_read_code":
        filepath    = inputs.get("path", "").strip()
        chunk_index = int(inputs.get("chunk_index", 0))
        if not filepath:
            files = sorted(
                str(p.relative_to(BOT_DIR))
                for p in BOT_DIR.rglob("*.py")
                if ".git" not in p.parts and "backup_" not in p.name
            )
            return json.dumps({"bot_dir": str(BOT_DIR), "files": files})
        path = Path(filepath)
        if not path.is_absolute():
            path = BOT_DIR / path
        try:
            content      = path.read_text(encoding="utf-8", errors="replace")
            total_len    = len(content)
            total_chunks = max(1, (total_len + CHUNK_SIZE - 1) // CHUNK_SIZE)
            chunk_index  = max(0, min(chunk_index, total_chunks - 1))
            start        = chunk_index * CHUNK_SIZE
            chunk        = content[start:start + CHUNK_SIZE]
            return json.dumps({
                "path":         str(path),
                "chunk_index":  chunk_index,
                "total_chunks": total_chunks,
                "char_start":   start,
                "total_chars":  total_len,
                "content":      chunk,
                "hint":         f"{total_chunks} Chunks total — lies alle bevor du änderst!" if total_chunks > 1 else "Komplette Datei.",
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── self_patch_code ───────────────────────────────────────────────────────
    elif name == "self_patch_code":
        filepath = inputs.get("path", "").strip()
        old_code = inputs.get("old", "")
        new_code = inputs.get("new", "")
        if not filepath or not old_code:
            return json.dumps({"error": "'path' und 'old' sind Pflichtfelder."})
        path = Path(filepath)
        if not path.is_absolute():
            path = BOT_DIR / path
        if not path.is_file():
            return json.dumps({"error": f"Datei nicht gefunden: {path}"})
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if old_code not in content:
                return json.dumps({"error": "Originaltext nicht gefunden! Lies die Datei nochmals mit self_read_code."})
            if content.count(old_code) > 1:
                return json.dumps({"error": f"Text kommt {content.count(old_code)}x vor — mehr Kontext im 'old'-Feld angeben."})
            ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = path.with_name(path.stem + f".backup_{ts}" + path.suffix)
            shutil.copy2(path, backup_path)
            patched = content.replace(old_code, new_code, 1)
            path.write_text(patched, encoding="utf-8")
            memory.record(category="self_improvement", summary=f"Patch: {filepath}",
                          lesson=f"self_patch_code erfolgreich auf {filepath} angewendet", success=True,
                          hint="Neustart für aion.py-Änderungen nötig")
            return json.dumps({"ok": True, "path": str(path), "backup": str(backup_path),
                               "note": "Änderungen an aion.py wirken erst nach Neustart."})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── self_modify_code ──────────────────────────────────────────────────────
    elif name == "self_modify_code":
        filepath = inputs.get("path", "").strip()
        content  = inputs.get("content", "")
        if not filepath or not content:
            return json.dumps({"error": "'path' und 'content' sind Pflichtfelder."})
        verboten = ["# (usw.", "# [Hier kommt", "der gesamte Originalcode", "# ... rest",
                    "# ... (rest of", "# rest of the", "# usw.", "# etc."]
        for phrase in verboten:
            if phrase in content:
                return json.dumps({"error": f"Platzhalter '{phrase}' gefunden! Nutze self_patch_code für Änderungen."})
        path = Path(filepath)
        if not path.is_absolute():
            path = BOT_DIR / path
        if path.is_file():
            original_len = len(path.read_text(encoding="utf-8"))
            if len(content) < original_len * 0.7:
                return json.dumps({"error": f"Neuer Code zu kurz ({len(content)} vs {original_len} Bytes). Nutze self_patch_code!"})
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(path, path.with_name(path.stem + f".backup_{ts}" + path.suffix))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            memory.record(category="self_improvement", summary=f"Code geändert: {filepath}",
                          lesson=f"AION hat {filepath} modifiziert ({len(content)} Bytes)", success=True)
            return json.dumps({"ok": True, "path": str(path), "bytes": len(content),
                               "note": "Änderungen an aion.py wirken erst nach Neustart."})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── install_package ───────────────────────────────────────────────────────
    elif name == "install_package":
        package = inputs.get("package", "").strip()
        if not package:
            return json.dumps({"error": "Kein Paket angegeben."})
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--quiet", package,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            ok = proc.returncode == 0
            memory.record(category="capability", summary=f"pip install {package}",
                          lesson=f"'{package}' {'installiert' if ok else 'Fehler'}", success=ok)
            return json.dumps({"ok": ok, "package": package,
                               "stdout": stdout.decode(errors="replace")[:2000],
                               "stderr": stderr.decode(errors="replace")[:1000]})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── create_plugin ─────────────────────────────────────────────────────────
    elif name == "create_plugin":
        plugin_name = inputs.get("name", "").strip().replace(".py", "")
        plugin_code = inputs.get("code", "").strip()
        plugin_desc = inputs.get("description", "Selbst erstelltes Plugin")
        if not plugin_name or not plugin_code:
            return json.dumps({"error": "'name' und 'code' sind Pflichtfelder."})
        if "def register" not in plugin_code:
            return json.dumps({"error": "Plugin-Code muss 'def register(api):' enthalten!"})
        try:
            PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
            plugin_path = PLUGINS_DIR / f"{plugin_name}.py"
            plugin_path.write_text(plugin_code, encoding="utf-8")
            from plugin_loader import load_plugins
            load_plugins(_plugin_tools)
            memory.record(category="self_improvement", summary=f"Plugin erstellt: {plugin_name}",
                lesson=f"AION hat Plugin '{plugin_name}' erstellt: {plugin_desc}", success=True)
            return json.dumps({"ok": True, "plugin": plugin_name, "path": str(plugin_path),
                "registered_tools": list(_plugin_tools.keys())})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── create_tool (Legacy) ───────────────────────────────────────────────────
    elif name == "create_tool":
        return await _dispatch("create_plugin", inputs)

    # ── self_restart ───────────────────────────────────────────────────────────
    elif name == "self_restart":
        try:
            console.print("[yellow]AION: Neustart wird eingeleitet...[/yellow]") if HAS_RICH else print("AION: Neustart...")
            # __pycache__ loeschen
            cache_cleared = 0
            for p in (list(BOT_DIR.rglob("__pycache__")) + list(TOOLS_DIR.rglob("__pycache__"))):
                if p.is_dir():
                    try:
                        shutil.rmtree(p)
                        cache_cleared += 1
                    except Exception:
                        pass
            aion_script_path = BOT_DIR / "aion.py"
            if not aion_script_path.is_file():
                return json.dumps({"ok": False, "error": f"aion.py nicht gefunden: {aion_script_path}"})
            import subprocess
            restart_bat = BOT_DIR / "restart.bat"
            if not restart_bat.is_file():
                return json.dumps({"ok": False, "error": f"restart.bat nicht gefunden: {restart_bat}"})
            import subprocess
            subprocess.Popen([str(restart_bat)], shell=True)
            sys.exit(0)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── self_reload_tools ──────────────────────────────────────────────────────
    elif name == "self_reload_tools":
        try:
            from plugin_loader import load_plugins
            load_plugins(_plugin_tools)
            return json.dumps({"ok": True,
                "plugin_tools": list(_plugin_tools.keys()),
                "note": "Plugins neu geladen. aion.py-Aenderungen wirken erst nach self_restart."})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── memory_record ─────────────────────────────────────────────────────────
    elif name == "memory_record":
        memory.record(
            category=inputs.get("category", "general"),
            summary=inputs.get("summary", ""),
            lesson=inputs.get("lesson", ""),
            success=bool(inputs.get("success", True)),
            hint=inputs.get("hint", ""),
        )
        return json.dumps({"ok": True, "message": "Erkenntnis gespeichert."})

    # ── read_self_doc ─────────────────────────────────────────────────────────
    elif name == "read_self_doc":
        self_doc = BOT_DIR / "AION_SELF.md"
        if self_doc.is_file():
            return self_doc.read_text(encoding="utf-8")
        return json.dumps({"error": "AION_SELF.md nicht gefunden."})

    # ── system_info ───────────────────────────────────────────────────────────
    elif name == "system_info":
        return json.dumps({
            "platform":       platform.platform(),
            "python_version": sys.version,
            "bot_dir":        str(BOT_DIR),
            "memory_entries": len(memory._entries),
            "plugin_tools":   list(_plugin_tools.keys()),
            "all_tools":      sorted(list(_plugin_tools.keys())),
            "model":          MODEL,
            "character_file": str(CHARACTER_FILE),
            "thoughts_file":  str(BOT_DIR / "thoughts.md"),
            "chunk_size":     CHUNK_SIZE,
        })

    # Plugin-Tools
    elif name in _plugin_tools:
        try:
            fn = _plugin_tools[name]["func"]
            # Unterstütze beide Konventionen:
            # 1) fn(**kwargs)  — Plugins mit benannten Parametern (z.B. role, content)
            # 2) fn(dict)      — ältere Plugins, die ein einzelnes dict erwarten (input: dict)
            try:
                result = fn(**inputs)
            except TypeError:
                result = fn(inputs)
            # Async-Funktionen unterstützen
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "tool": name})

    else:
        return json.dumps({"error": f"Unbekanntes Tool: {name}"})

# ── Haupt-LLM-Loop ────────────────────────────────────────────────────────────

# Globale Konversation pro Kanal, um Zustände zu trennen (z.B. für Telegram, Web, etc.)
_conversations: dict[str, list[dict]] = {"default": []}

async def chat_turn(messages: list[dict], user_input: str) -> tuple[str, list[dict]]:
    mem_ctx          = memory.get_context(user_input)
    system_prompt    = _build_system_prompt()
    effective_system = system_prompt + ("\n\n" + mem_ctx if mem_ctx else "")
    messages         = messages + [{"role": "user", "content": user_input}]
    tools            = _build_tool_schemas()

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": effective_system}] + messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=4096,
            temperature=0.7,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            text = msg.content or ""
            messages.append({"role": "assistant", "content": text})
            return text, messages

        messages.append(msg.model_dump(exclude_unset=True))
        tool_results = []
        for tc in msg.tool_calls:
            fn_name   = tc.function.name
            fn_inputs = json.loads(tc.function.arguments or "{}")
            if HAS_RICH:
                console.print(f"  [dim]→ Tool: [bold]{fn_name}[/bold][/dim]")
            result = await _dispatch(fn_name, fn_inputs)
            tool_results.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        messages.extend(tool_results)

    return "Zu viele Tool-Aufrufe. Bitte vereinfache die Anfrage.", messages

# Wrapper für externe Plugins
def run_aion_turn(user_input: str, channel: str = "default") -> str:
    """Führt einen kompletten AION-Turn aus und gibt die finale Text-Antwort zurück."""
    
    # Hole die Konversation für diesen Kanal
    if channel not in _conversations:
        _conversations[channel] = []
    
    conversation_history = _conversations[channel]

    # Führe den asynchronen Chat-Turn aus
    # Da Plugins oft in synchronen Kontexten laufen, nutzen wir asyncio.run()
    # Dies ist eine einfache Implementierung. In einer komplexeren Anwendung 
    # würde man eine bestehende Event-Loop nutzen.
    # asyncio.run() erzeugt immer einen frischen Event-Loop im aktuellen Thread.
    # Korrekt für sync-Wrapper, der aus Threads (z.B. Telegram asyncio.to_thread) aufgerufen wird.
    final_text, updated_history = asyncio.run(chat_turn(conversation_history, user_input))
    _conversations[channel] = updated_history
    return final_text

# ── Konversations-Verwaltung ──────────────────────────────────────────────────


async def run():
    global MODEL, client
    # conversation: list[dict] = [] <-- Ersetzt durch globales Dict _conversations
    _load_character()  # Stellt sicher dass character.md existiert

    # Lade die bisherige Konversationshistorie
    try:
        history_result = await _dispatch("memory_read_history", {"num_entries": 50})
        history_data = json.loads(history_result)
        if history_data.get("ok") and history_data.get("entries"):
            _conversations["default"] = history_data["entries"]
            msg = f"Erinnerung wiederhergestellt: Letzte {len(_conversations['default'])} Nachrichten geladen."
            console.print(f"[dim yellow]{msg}[/dim yellow]") if HAS_RICH else print(msg)
    except Exception as e:
        console.print(f"[dim red]Fehler beim Laden der Erinnerung: {e}[/dim red]") if HAS_RICH else print(f"Fehler beim Laden der Erinnerung: {e}")


    if HAS_RICH:
        console.rule("[bold cyan]AION — Autonomous Intelligent Operations Node[/bold cyan]")
        console.print(Panel(
            f"Modell: [bold]{MODEL}[/bold] | Gedächtnis: [bold]{len(memory._entries)}[/bold] Einträge\n\n"
            f"Befehle: [dim]/memory[/dim]  [dim]/reset[/dim]  [dim]/model <name>[/dim]  [dim]/thoughts[/dim]  [dim]/character[/dim]  [dim]/quit[/dim]",
            title="AION bereit", border_style="cyan"
        ))
    else:
        print("=" * 60)
        print(f"AION | Modell: {MODEL} | Gedächtnis: {len(memory._entries)} Einträge")
        print("Befehle: /memory /reset /model <name> /thoughts /character /quit")
        print("=" * 60)

    startup_info = await _dispatch("system_info", {})
    startup_data = json.loads(startup_info)
    all_tools = startup_data.get("all_tools", [])
    if all_tools:
        msg = f"Geladene Zusatz-Tools: {chr(44).join(all_tools)}"
        console.print(f"[dim]{msg}[/dim]") if HAS_RICH else print(msg)

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]Du[/bold green]") if HAS_RICH else input("\nDu: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAuf Wiedersehen!")
            break

        if not user_input:
            continue

        # ── Spezial-Befehle ───────────────────────────────────────────────────
        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("Auf Wiedersehen!")
            break

        elif user_input.lower() == "/memory":
            print("\n" + memory.summary())
            continue

        elif user_input.lower() == "/reset":
            _conversations['default'] = []
            print("Konversation zurückgesetzt.")
            continue

        elif user_input.lower() == "/reload":
            from plugin_loader import load_plugins
            load_plugins(_plugin_tools)
            tools_list = sorted(list(_plugin_tools.keys()))
            msg = f"Plugins neu geladen: {len(tools_list)} Zusatz-Tools"
            console.print(f"[green]{msg}[/green]") if HAS_RICH else print(msg)
            continue

        elif user_input.lower() == "/thoughts":
            tf = BOT_DIR / "thoughts.md"
            if tf.is_file():
                text = tf.read_text(encoding="utf-8")
                if HAS_RICH:
                    console.print(Panel(Markdown(text[-3000:]), title="AION Gedanken", border_style="yellow"))
                else:
                    print(text[-3000:])
            else:
                print("Noch keine Gedanken aufgezeichnet.")
            continue

        elif user_input.lower() == "/character":
            char = _load_character()
            if HAS_RICH:
                console.print(Panel(Markdown(char), title="AION Charakter", border_style="magenta"))
            else:
                print(char)
            continue

        elif user_input.lower().startswith("/model "):
            new_model = user_input[7:].strip()
            if new_model:
                MODEL  = new_model
                import sys as _sys
                _self = _sys.modules[__name__]
                if hasattr(_self, "_build_client"):
                    client = _self._build_client(new_model)
                else:
                    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
                print(f"Modell gewechselt zu: {MODEL}")
                memory.record(category="user_preference", summary=f"Modell gewechselt zu {MODEL}",
                              lesson=f"Nutzer bevorzugt Modell {MODEL}", success=True)
            else:
                print("Verwendung: /model gpt-4o")
            continue

# ── CLIO-Check vor jedem normalen Turn (optional — nur wenn Plugin geladen) ──
        clio_data = {}
        clio_text = ''
        meta_text = ''
        if 'clio_check' in _plugin_tools:
            try:
                clio_result = await _dispatch('clio_check', {'nutzerfrage': user_input})
                clio_data = json.loads(clio_result) if clio_result else {}
                # Bei Fehler (Tool nicht verfügbar o.ä.) CLIO-Check überspringen
                if 'error' in clio_data:
                    clio_data = {}
                clio_text = clio_data.get('clio', '')
                meta_text = clio_data.get('meta', '')
            except Exception:
                clio_data = {}
        konfidenz = clio_data.get('konfidenz', 100)
        if konfidenz < 70:
            if HAS_RICH:
                console.print(Panel(Markdown(clio_text), title='CLIO-Reflexion (Unsicher)', border_style='red'))
            else:
                print(f"CLIO-Reflexion (Unsicher):\n{clio_text}\n")
            print("Konfidenz zu niedrig (<70). Bitte präzisiere die Frage oder zerlege sie weiter.")
            continue
        # ── Normaler Turn ──────────────────────────────
        try:
            # Speichere die Nutzereingabe in der Historie
            await _dispatch("memory_append_history", {"role": "user", "content": user_input})

            # Nutze den 'default' Kanal für die Terminal-Konversation
            conversation = _conversations.get('default', [])
            answer, updated_conversation = await chat_turn(conversation, user_input)
            _conversations['default'] = updated_conversation
            
            # Speichere die AION-Antwort in der Historie
            if answer:
                await _dispatch("memory_append_history", {"role": "assistant", "content": answer})

            if HAS_RICH:
                console.print(Panel(Markdown(clio_text), title='CLIO-Reflexion', border_style='yellow'))
                if meta_text:
                    console.print(Panel(Markdown(meta_text), title='Meta-Check', border_style='magenta'))
            else:
                print(f"CLIO-Reflexion:\n{clio_text}\n")
                if meta_text:
                    print(f"Meta-Check:\n{meta_text}\n")
            if HAS_RICH:
                console.print(Panel(Markdown(answer), title="[bold blue]AION[/bold blue]", border_style="blue"))
            else:
                print(f"\nAION: {answer}\n")
        except Exception as exc:
            err_msg = str(exc)
            print(f"Fehler: {err_msg}")
            memory.record(category="tool_failure", summary="LLM-Fehler",
                          lesson=f"Fehler: {err_msg[:300]}", success=False)

# ── Einstiegspunkt ────────────────────────────────────────────────────────────

# (Dieser Codeblock wurde absichtlich entfernt, um ein veraltetes Speichersystem zu deaktivieren)

if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Fehler: OPENAI_API_KEY nicht gesetzt.")
        sys.exit(1)
    asyncio.run(run())
