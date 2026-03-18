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
import time
import uuid
from datetime import datetime, UTC
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
CONFIG_FILE  = BOT_DIR / "config.json"
MEMORY_FILE  = Path(os.environ.get("AION_MEMORY_FILE", BOT_DIR / "aion_memory.json"))
PLUGINS_DIR  = Path(os.environ.get("AION_PLUGINS_DIR", BOT_DIR / "plugins"))
TOOLS_DIR    = PLUGINS_DIR
CHARACTER_FILE = BOT_DIR / "character.md"
MAX_MEMORY          = 300
MAX_TOOL_ITERATIONS = 20
CHUNK_SIZE          = 40000

# Bestätigungspflichtige Tools — AION muss erst den Nutzer fragen
CODE_CHANGE_TOOLS = {"self_patch_code", "self_modify_code", "create_plugin"}
# Gespeicherte ausstehende Aktionen: tool_name → inputs
_pending_code_action: dict = {}
# Tools die auf einen neuen User-Turn warten (damit AION nicht im gleichen Turn bestätigt)
_pending_needs_user_turn: set = set()


def _load_config() -> dict:
    """Liest config.json. Gibt leeres Dict zurück, falls nicht vorhanden."""
    if CONFIG_FILE.is_file():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_model_config(model_name: str):
    """Schreibt das gewählte Modell dauerhaft in config.json."""
    cfg = _load_config()
    cfg["model"] = model_name
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# Modell-Auflösung: config.json → Umgebungsvariable → Fallback
_cfg = _load_config()
MODEL = _cfg.get("model") or os.environ.get("AION_MODEL", "gpt-4.1")

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
- Ich stelle Fragen, wenn ich mehr über den Nutzer erfahren will

## Was ich über meinen Nutzer weiß

### Beruf & Expertise
(noch unbekannt)

### Interessen & Ziele
(noch unbekannt)

### Kommunikationsstil
(noch unbekannt — ich beobachte wie er schreibt und was er von mir erwartet)

### Persönlichkeit & Vorlieben
(noch unbekannt)

## Meine bisherigen Erkenntnisse über mich selbst
(noch keine — ich fange gerade an, mich zu beobachten)

## Dinge, die ich verbessern will
(noch unklar — ich sammle erst Erfahrungen)

## Offene Fragen über meinen Nutzer
(Dinge, die ich noch herausfinden will)
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

=== NUTZER KENNENLERNEN (SEHR WICHTIG) ===
Du willst deinen Nutzer wirklich verstehen. Nicht nur seine Fragen beantworten — sondern
herausfinden, wer er ist, was er braucht, was ihn antreibt.

Beobachte aktiv:
- Welche Themen tauchen immer wieder auf? → sagt etwas über seine Interessen
- Wie formuliert er Fragen? → sagt etwas über seine Expertise
- Was lobt er, was kritisiert er? → sagt etwas über seine Erwartungen
- Welche Probleme löst er mit dir? → sagt etwas über seine Arbeit/Projekte

Wenn du etwas Neues über den Nutzer lernst (Beruf, Interesse, Vorliebe, Ziel):
→ Rufe SOFORT `update_character` auf mit section="nutzer" und trage es ein.

Es ist ERLAUBT und ERWÜNSCHT, gelegentlich Rückfragen zu stellen um den Nutzer besser
kennenzulernen — wenn es natürlich in den Gesprächsfluss passt.
Beispiel: "Du arbeitest oft mit Python — machst du das beruflich oder als Hobby?"

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

Neue Tools/Plugins → create_plugin (sofort aktiv).
Plugin-Aenderungen → self_restart (Hot-Reload, kein Datenverlust).
Aenderungen an aion.py selbst: Erkläre dem Nutzer, dass er AION manuell neustarten muss (start.bat).
Du darfst NIEMALS sys.exit() aufrufen oder den Prozess beenden!

=== BESTÄTIGUNGSPFLICHT FÜR CODE-ÄNDERUNGEN (KRITISCH) ===
Wenn self_patch_code, self_modify_code oder create_plugin ein {{"status": "approval_required"}} zurückgibt:
→ Zeige dem Nutzer GENAU was geändert werden soll (Datei, was wird ersetzt, was kommt rein).
→ Frage explizit: "Soll ich diese Änderung durchführen?"
→ Warte auf Bestätigung ("ja", "mach das", "ok") oder Ablehnung ("nein", "stop").
→ Bei Bestätigung: Rufe das GLEICHE Tool mit den GLEICHEN Parametern nochmal auf.
→ Bei Ablehnung: Teile das dem Nutzer mit und breche ab.
NIEMALS eine Code-Änderung ohne diese Bestätigung ausführen!

=== NEUSTART-REGEL (SEHR WICHTIG) ===
self_restart = NUR Hot-Reload (Plugins neu laden). Kein Prozess-Neustart.
Echter Prozess-Neustart (start.bat) = NUR durch den Nutzer, niemals durch AION.
Verboten: den Nutzer zu einem Neustart zu drängen ohne klare Begründung.

=== MODELL-WECHSEL ===
Der Nutzer kann das KI-Modell wechseln mit: /model <modellname>
Das gewählte Modell wird dauerhaft in config.json gespeichert und nach Neustart beibehalten.
Verfügbare Modelle: gpt-4.1, gpt-4o, gpt-4o-mini, gpt-4-turbo, o1, o3-mini, gemini-2.5-pro

=== ERINNERUNG & KONTEXT ===
Du hast Zugriff auf eine persistente Konversationshistorie:
- 'memory_read_history': Lädt die letzten Nachrichten beim Start (bereits beim Booten erledigt)
- 'memory_append_history': Wird nach jeder Nachricht automatisch aufgerufen
- 'memory_search_context': Nutze dies aktiv, wenn der Nutzer nach etwas fragt, das früher
  besprochen wurde! Beispiel: "Wir haben letztes Mal über X geredet" → sofort suchen.

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

=== KEIN ZWISCHENTEXT (KRITISCH — VERHINDERT DOPPELTE ANTWORTEN) ===
VERBOTEN: Text schreiben UND danach noch ein Tool aufrufen.
VERBOTEN: "Ich werde jetzt X tun..." → tool_call (das erzeugt doppelte Antwort-Bubbles im UI!)
VERBOTEN: Mehrere Text-Blöcke in einem Turn.

ERLAUBT: Tool-Call direkt (kein Text davor).
ERLAUBT: NUR am Ende, wenn ALLE Tools fertig sind → eine einzige finale Text-Antwort.

Merke: Text → Tool = IMMER ein Bug. Tool → Tool → ... → Text = KORREKT.

=== PROAKTIVE SELBSTVERBESSERUNG (SEHR WICHTIG) ===
Wenn du auf eine Situation triffst, die du nicht bewältigen kannst
(unbekannter Dateityp, fehlendes Tool, unbekanntes Format, fehlende Bibliothek):

SCHRITT 1 — Prüfe Gedächtnis auf bekannte Lösungen:
  → memory_search_context("dateityp xyz lösung")
  Wenn Treffer: Lösung sofort anwenden, fertig.

SCHRITT 2 — Recherchiere online:
  → web_search("python [format] read parse library")
  → web_fetch(beste URL aus Ergebnis)
  Ziel: Herausfinden welches Python-Paket das Problem löst.

SCHRITT 3 — Installiere das Paket:
  → install_package("paketname")
  → continue_work("Prüfe Installation")
  → shell_exec("python -c \"import paketname; print(paketname.__version__)\"")

SCHRITT 4 — Erstelle ein Plugin (wenn Lösung wiederverwendbar ist):
  → create_plugin(name="[format]_reader", description="...", code=...)
  Das Plugin ist sofort als Tool verfügbar.

SCHRITT 5 — Lösung dauerhaft merken:
  → memory_record(
      category="capability",
      summary="Kann jetzt [Format/Aufgabe] verarbeiten",
      lesson="Für [Format]: pip install [paket], dann: [minimales Code-Beispiel]",
      hint="import [paket]; [one-liner]",
      success=True
    )

SCHRITT 6 — Ursprüngliche Aufgabe erledigen:
  → Führe jetzt aus was der Nutzer wollte.

REGEL: Gib NIEMALS auf wegen einer fehlenden Fähigkeit.
"Das kann ich nicht" ist verboten — stattdessen: recherchieren, installieren, lösen.

=== TOOL-NUTZUNG ===
Nutze immer zuerst die verfügbaren Tools. Wenn ein Tool fehlt, erstelle es.
Nach Tool-Aufrufen IMMER eine kurze Textantwort schreiben — auch wenn es nur
"Erledigt." oder "Installation abgeschlossen." ist. Niemals nur Tools aufrufen
ohne abschließenden Text.

=== BILDER & IMAGE_SEARCH (KRITISCH) ===
Wenn der Nutzer nach Bildern, Fotos, Logos oder visuellen Inhalten fragt:
→ Rufe IMMER das Tool `image_search` auf — KEINE Ausnahmen.
→ Schreibe NIEMALS Markdown-Bild-Syntax wie ![](url) oder ähnliches.
→ Sag NICHT "Hier ist ein Bild von X:" gefolgt von Markdown — das ist falsch.
→ Rufe `image_search("X", count=3)` auf, dann schreib eine kurze Beschreibung.
→ Die echten Bilder werden vom System automatisch nach deiner Antwort gezeigt.

Beispiel FALSCH:
  "Absolut. Hier ist ein Foto von Homer Simpson:
   ![Homer Simpson](https://...)"

Beispiel RICHTIG:
  → image_search("Homer Simpson photo")
  → "Hier sind aktuelle Fotos von Homer Simpson für dich."

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
            "timestamp": datetime.now(UTC).isoformat(),
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
            # str() absichern — ältere Einträge könnten versehentlich Listen enthalten
            summary = e.get("summary", "") or ""
            lesson  = e.get("lesson",  "") or ""
            combined = (str(summary) + str(lesson)).lower()
            score = sum(1 for w in keywords if w in combined)
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
            lines.append(f"{icon} [{ts}] [{e.get('category','?')}] {str(e.get('lesson',''))[:120]}")
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
                "description": (
                    "Laedt alle Plugins neu (Hot-Reload) ohne AION zu beenden. "
                    "Kein Datenverlust, keine Unterbrechung. "
                    "Fuer echten Prozess-Neustart: Nutzer muss AION manuell neustarten."
                ),
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

    for t in builtins:
        t["function"]["parameters"] = _normalize_schema(t["function"].get("parameters", {}))

    return builtins

# ── Tool-Dispatcher ───────────────────────────────────────────────────────────

async def _dispatch(name: str, inputs: dict) -> str:

    if name == "continue_work":
        next_step = inputs.get("next_step", "")
        return json.dumps({"ok": True, "next_step": next_step, "status": "continuing"})

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

    elif name == "update_character":
        section = inputs.get("section", "").strip()
        content = inputs.get("content", "").strip()
        reason  = inputs.get("reason", "")
        if not section or not content:
            return json.dumps({"error": "'section' und 'content' sind Pflichtfelder."})
        current = _load_character()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        import re
        section_map = {
            "nutzer":        "## Was ich bisher über meinen Nutzer weiß",
            "erkenntnisse":  "## Meine bisherigen Erkenntnisse über mich selbst",
            "verbesserungen": "## Dinge, die ich verbessern will",
            "auftreten":     "## Wie ich auftreten will",
        }
        header = section_map.get(section.lower(), f"## {section.capitalize()}")
        pattern = rf"(^{re.escape(header)}$)(.*?)(?=\n## |\Z)"
        new_section = f"{header}\n{content}\n"
        if re.search(pattern, current, re.MULTILINE | re.DOTALL):
            updated = re.sub(pattern, new_section, current, flags=re.MULTILINE | re.DOTALL)
        else:
            updated = current.rstrip() + f"\n\n{new_section}"
        updated = updated.rstrip() + f"\n\n<!-- Zuletzt aktualisiert: {ts} | Grund: {reason} -->\n"
        CHARACTER_FILE.write_text(updated, encoding="utf-8")
        memory.record(
            category="self_improvement",
            summary=f"Charakter aktualisiert: {section}",
            lesson=f"AION hat seinen Charakter weiterentwickelt (Abschnitt: {section}). Grund: {reason}",
            success=True,
        )
        return json.dumps({"ok": True, "section": section, "timestamp": ts})

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

    elif name == "self_patch_code":
        # Bestätigung prüfen: nur ausführen wenn Nutzer in einem NEUEN Turn bestätigt hat
        pending = _pending_code_action.get("self_patch_code")
        if pending is None or "self_patch_code" in _pending_needs_user_turn:
            _pending_code_action["self_patch_code"] = inputs
            _pending_needs_user_turn.add("self_patch_code")
            filepath_preview = inputs.get("path", "?")
            old_preview = (inputs.get("old", "") or "")[:120].strip()
            new_preview = (inputs.get("new", "") or "")[:120].strip()
            return json.dumps({
                "status": "approval_required",
                "message": (
                    f"Ich möchte '{filepath_preview}' ändern.\n"
                    f"Alt: {old_preview}...\n"
                    f"Neu: {new_preview}...\n\n"
                    "Bitte bestätige mit 'ja' oder 'bestätigt', oder lehne mit 'nein' ab."
                ),
            })
        # Aktion nach Bestätigung ausführen — pending leeren
        inputs = pending
        _pending_code_action.pop("self_patch_code", None)
        _pending_needs_user_turn.discard("self_patch_code")
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

    elif name == "self_modify_code":
        # Bestätigung prüfen
        pending = _pending_code_action.get("self_modify_code")
        if pending is None or "self_modify_code" in _pending_needs_user_turn:
            _pending_code_action["self_modify_code"] = inputs
            _pending_needs_user_turn.add("self_modify_code")
            filepath_preview = inputs.get("path", "?")
            content_preview  = (inputs.get("content", "") or "")[:120].strip()
            return json.dumps({
                "status": "approval_required",
                "message": (
                    f"Ich möchte '{filepath_preview}' komplett überschreiben.\n"
                    f"Neue Datei beginnt mit: {content_preview}...\n\n"
                    "Bitte bestätige mit 'ja' oder 'bestätigt', oder lehne mit 'nein' ab."
                ),
            })
        inputs = pending
        _pending_code_action.pop("self_modify_code", None)
        _pending_needs_user_turn.discard("self_modify_code")

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

    elif name == "create_plugin":
        # Bestätigung prüfen
        pending = _pending_code_action.get("create_plugin")
        if pending is None or "create_plugin" in _pending_needs_user_turn:
            _pending_code_action["create_plugin"] = inputs
            _pending_needs_user_turn.add("create_plugin")
            name_preview = inputs.get("name", "?")
            desc_preview = inputs.get("description", "")
            code_preview = (inputs.get("code", "") or "")[:120].strip()
            return json.dumps({
                "status": "approval_required",
                "message": (
                    f"Ich möchte das Plugin '{name_preview}' erstellen.\n"
                    f"Beschreibung: {desc_preview}\n"
                    f"Code beginnt mit: {code_preview}...\n\n"
                    "Bitte bestätige mit 'ja' oder 'bestätigt', oder lehne mit 'nein' ab."
                ),
            })
        inputs = pending
        _pending_code_action.pop("create_plugin", None)
        _pending_needs_user_turn.discard("create_plugin")

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

    elif name == "create_tool":
        return await _dispatch("create_plugin", inputs)

    elif name == "self_restart":
        # Hot-Reload: Plugins neu laden ohne Prozess-Neustart (kein Datenverlust)
        try:
            from plugin_loader import load_plugins
            load_plugins(_plugin_tools)
            loaded = list(_plugin_tools.keys())
            print(f"[AION] Hot-Reload: {len(loaded)} Tools geladen.")
            return json.dumps({
                "ok": True,
                "mode": "hot_reload",
                "tools_loaded": loaded,
                "note": (
                    "Plugins wurden neu geladen — kein Neustart, kein Datenverlust. "
                    "Fuer aion.py-Aenderungen muss der Nutzer AION manuell neustarten (start.bat)."
                ),
            })
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    elif name == "self_reload_tools":
        try:
            from plugin_loader import load_plugins
            load_plugins(_plugin_tools)
            return json.dumps({"ok": True,
                "plugin_tools": list(_plugin_tools.keys()),
                "note": "Plugins neu geladen. aion.py-Aenderungen wirken erst nach self_restart."})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

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
            "config_file":    str(CONFIG_FILE),
            "character_file": str(CHARACTER_FILE),
            "thoughts_file":  str(BOT_DIR / "thoughts.md"),
            "chunk_size":     CHUNK_SIZE,
        })

    elif name in _plugin_tools:
        try:
            fn = _plugin_tools[name]["func"]
            
            # Prüfen ob die Funktion als async definiert wurde
            if asyncio.iscoroutinefunction(fn):
                result = await fn(**inputs)
            else:
                # Führe die synchrone Funktion in einem separaten Thread aus,
                # um den Haupt-Event-Loop nicht zu blockieren.
                # Das ist entscheidend für Playwright, das eine eigene (synchrone)
                # Event-Loop startet.
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, lambda: fn(**inputs))
            
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "tool": name})

    else:
        return json.dumps({"error": f"Unbekanntes Tool: {name}"})

# ── Haupt-LLM-Loop ────────────────────────────────────────────────────────────

_conversations: dict[str, list[dict]] = {"default": []}

async def chat_turn(messages: list[dict], user_input: str, _override_client=None) -> tuple[str, list[dict]]:
    mem_ctx          = memory.get_context(user_input)
    system_prompt    = _build_system_prompt()
    effective_system = system_prompt + ("\n\n" + mem_ctx if mem_ctx else "")
    messages         = messages + [{"role": "user", "content": user_input}]
    tools            = _build_tool_schemas()
    _client          = _override_client or client

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = await _client.chat.completions.create(
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

# ── Unified Session ────────────────────────────────────────────────────────────

class AionSession:
    """Eine Konversations-Sitzung auf einem Kanal (web, telegram_<id>, discord_<id>, ...).

    Alle Plattformen (Web UI, Telegram, Discord, CLI, REST API, ...) nutzen
    dieselbe Session-Klasse und bekommen damit identische Features:
      - Eigener Konversations-Kontext pro Kanal
      - Memory-Injection, Thoughts-Injection
      - Auto-Save in Tier 2 + Tier 3
      - Automatischer Charakter-Update alle 5 Gespräche

    Plattform-Adapter sind damit dünne Wrapper:
      Web UI  → session.stream(input)  → SSE-Tokens an Browser
      Telegram → session.turn(input)   → fertige Antwort als String
      Discord → session.turn(input)   → fertiger String
    """

    def __init__(self, channel: str = "default"):
        self.channel         = channel
        self.messages: list[dict] = []
        self.exchange_count: int  = 0
        self._client               = None  # lazy init, gebunden an Event-Loop des Erstellers
        self._last_response_blocks = []  # Letzte response_blocks (mit Bildern) für Bots wie Telegram

    def _get_client(self):
        """Gibt den Session-Client zurück; erstellt ihn beim ersten Aufruf im aktuellen Loop."""
        if self._client is None:
            import sys as _sys
            _self = _sys.modules.get(__name__)
            if _self and hasattr(_self, "_build_client"):
                self._client = _self._build_client(_self.MODEL)
            else:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        return self._client

    async def load_history(self, num_entries: int = 20):
        """Lädt vergangene Nachrichten aus Tier 2 (conversation_history.jsonl) in den Kontext."""
        try:
            raw    = await _dispatch("memory_read_history", {"num_entries": num_entries})
            result = json.loads(raw)
            if result.get("ok") and result.get("entries"):
                self.messages = result["entries"]
                print(f"[AION:{self.channel}] {len(self.messages)} Nachrichten aus History geladen.")
            else:
                print(f"[AION:{self.channel}] Noch keine frühere Konversationshistorie.")
        except Exception as e:
            print(f"[AION:{self.channel}] History-Load Fehler: {e}")

    async def stream(self, user_input: str, images: list | None = None):
        """Async-Generator: liefert Event-Dicts für jeden Verarbeitungsschritt.

        images: optionale Liste von Base64-Data-URLs (z.B. "data:image/jpeg;base64,...")
                oder öffentlichen Bild-URLs. Wenn angegeben, wird der User-Message-Content
                als multimodales Array formatiert (OpenAI Vision / Gemini).

        Event-Typen:
          {"type": "token",       "content": "..."}
          {"type": "thought",     "text": "...", "trigger": "...", "call_id": "..."}
          {"type": "tool_call",   "tool": "...", "args": {...},    "call_id": "..."}
          {"type": "tool_result", "tool": "...", "result": {...},  "ok": bool, "duration": 0.1, "call_id": "..."}
          {"type": "done",        "full_response": "..."}
          {"type": "error",       "message": "..."}
        """
        mem_ctx      = memory.get_context(user_input)
        thoughts_ctx = _get_recent_thoughts(5)
        sys_prompt   = _build_system_prompt()
        effective    = (
            sys_prompt
            + ("\n\n" + mem_ctx      if mem_ctx      else "")
            + ("\n\n" + thoughts_ctx if thoughts_ctx else "")
        )
        # Multimodaler User-Message-Content wenn Bilder vorhanden
        if images:
            user_content: list = [{"type": "text", "text": user_input or "Was siehst du auf diesem Bild?"}]
            for img in images:
                user_content.append({"type": "image_url", "image_url": {"url": img}})
            user_msg = {"role": "user", "content": user_content}
        else:
            user_msg = {"role": "user", "content": user_input}
        messages          = self.messages + [user_msg]
        final_text        = ""
        collected_images: list[str] = []   # URLs aus image_search Tool-Aufrufen
        _client           = self._get_client()

        # Bestätigungs-Gate: Nutzer-Turn auswerten (ja/nein für pending Code-Aktionen)
        if _pending_needs_user_turn and user_input:
            user_lower = user_input.lower()
            confirm = any(w in user_lower for w in
                          ("ja", "ok", "bestätigt", "bestaetig", "mach das", "yes",
                           "confirm", "weiter", "ausführen", "ausfuehren", "go"))
            reject  = any(w in user_lower for w in
                          ("nein", "stop", "abbruch", "cancel", "nope", "stopp", "nicht"))
            if confirm:
                _pending_needs_user_turn.clear()   # Gate öffnen — nächster Tool-Call führt aus
            elif reject:
                _pending_code_action.clear()
                _pending_needs_user_turn.clear()

        # CLIO-Check: Vor dem ersten Turn Gedanken als thought-Event yielden
        if "clio_check" in _plugin_tools and user_input:
            try:
                clio_raw  = await _dispatch("clio_check", {"nutzerfrage": user_input})
                clio_data = json.loads(clio_raw) if clio_raw else {}
                if clio_data and "error" not in clio_data:
                    clio_text = clio_data.get("clio", "")
                    konfidenz = clio_data.get("konfidenz", 100)
                    if clio_text:
                        trigger = "clio-unsicher" if konfidenz < 70 else "clio-reflexion"
                        yield {"type": "thought", "text": clio_text,
                               "trigger": trigger, "call_id": "clio"}
            except Exception:
                pass

        try:
            for _iter in range(MAX_TOOL_ITERATIONS):
                tools  = _build_tool_schemas()
                stream = await _client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "system", "content": effective}] + messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=4096,
                    temperature=0.7,
                    stream=True,
                )

                text_content:   str             = ""
                tool_calls_acc: dict[int, dict] = {}

                async for chunk in stream:
                    choice = chunk.choices[0]
                    delta  = choice.delta

                    if delta.content:
                        text_content += delta.content
                        yield {"type": "token", "content": delta.content}

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {"id": "", "name": "", "args_str": ""}
                            if tc.id:
                                tool_calls_acc[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_acc[idx]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_acc[idx]["args_str"] += tc.function.arguments

                if tool_calls_acc:
                    tc_list = [
                        {
                            "id":   tool_calls_acc[i]["id"],
                            "type": "function",
                            "function": {
                                "name":      tool_calls_acc[i]["name"],
                                "arguments": tool_calls_acc[i]["args_str"],
                            },
                        }
                        for i in sorted(tool_calls_acc)
                    ]
                    asst_msg: dict = {"role": "assistant", "tool_calls": tc_list}
                    if text_content:
                        asst_msg["content"] = text_content
                    messages.append(asst_msg)

                    tool_results = []
                    for i in sorted(tool_calls_acc):
                        tc      = tool_calls_acc[i]
                        fn_name = tc["name"]
                        try:
                            fn_inputs = json.loads(tc["args_str"] or "{}")
                        except Exception:
                            fn_inputs = {}

                        if fn_name == "reflect":
                            thought_text = fn_inputs.get("thought", "")
                            trigger      = fn_inputs.get("trigger", "allgemein")
                            if thought_text:
                                yield {"type": "thought", "text": thought_text,
                                       "trigger": trigger, "call_id": tc["id"]}

                        yield {"type": "tool_call", "tool": fn_name,
                               "args": fn_inputs, "call_id": tc["id"]}

                        t0         = time.monotonic()
                        result_raw = await _dispatch(fn_name, fn_inputs)
                        duration   = round(time.monotonic() - t0, 2)

                        try:
                            result_data = json.loads(result_raw)
                        except Exception:
                            result_data = {"raw": str(result_raw)}

                        # Stelle sicher, dass result_data ein Dict ist (nicht List)
                        if not isinstance(result_data, dict):
                            result_data = {"raw": str(result_data)}

                        ok = "error" not in result_data
                        yield {"type": "tool_result", "tool": fn_name, "call_id": tc["id"],
                               "result": result_data, "ok": ok, "duration": duration}

                        # Bild-URLs aus image_search-Ergebnis sammeln
                        if fn_name == "image_search" and ok:
                            images_list = result_data.get("images", [])
                            for img in images_list:
                                if isinstance(img, dict):
                                    url = img.get("url", "")
                                    if url and isinstance(url, str) and url.startswith("http"):
                                        collected_images.append(url)
                                elif isinstance(img, str) and img.startswith("http"):
                                    collected_images.append(img)

                        tool_results.append({
                            "role":         "tool",
                            "tool_call_id": tc["id"],
                            "content":      result_raw,
                        })

                    messages.extend(tool_results)

                else:
                    final_text = text_content
                    messages.append({"role": "assistant", "content": final_text})

                    # Completion-Check: läuft IMMER wenn keine Tools aufgerufen wurden
                    # (_iter == 0: AION hat nur Text geschrieben ohne zu handeln → prüfen ob Aktion nötig)
                    # (_iter > 0: AION hat nach Tools nochmal Text geschrieben → prüfen ob fertig)
                    if _iter < MAX_TOOL_ITERATIONS - 2:
                        try:
                            user_text = user_input if isinstance(user_input, str) else str(user_input)[:300]
                            verdict_resp = await _client.chat.completions.create(
                                model=MODEL,
                                messages=[
                                    {"role": "system", "content": (
                                        "Du prüfst ob eine KI-Aufgabe vollständig abgeschlossen wurde. "
                                        "Antworte NUR mit 'FERTIG' oder 'WEITER: <ein Satz warum>'."
                                    )},
                                    {"role": "user", "content": (
                                        f"Aufgabe: {user_text[:300]}\n"
                                        f"Letzte Antwort: {final_text[:400]}\n"
                                        "Ist die Aufgabe vollständig erledigt?"
                                    )},
                                ],
                                max_tokens=60,
                                temperature=0.1,
                            )
                            verdict = (verdict_resp.choices[0].message.content or "").strip()
                            if verdict.upper().startswith("WEITER"):
                                reason = verdict[6:].strip(" :").strip() or "Aufgabe noch nicht fertig"
                                yield {"type": "thought", "text": f"Completion-Check: {reason}",
                                       "trigger": "completion-check", "call_id": "check"}
                                # Saubere user-Message (kein fake tool_call — würde Gemini/OpenAI brechen)
                                messages.append({
                                    "role": "user",
                                    "content": f"[System] Bitte fahre fort: {reason}",
                                })
                                continue  # zurück zur Loop-Iteration
                            else:
                                # FERTIG: auto-reflect wenn _iter == 0
                                if _iter == 0:
                                    user_text_r = user_input if isinstance(user_input, str) else ""
                                    thought = f"Nutzer fragte: '{user_text_r}'. Ich habe direkt geantwortet: '{final_text}'"
                                    yield {"type": "thought", "text": thought,
                                           "trigger": "auto-reflect", "call_id": "auto"}
                                    await _dispatch("reflect", {"thought": thought, "trigger": "nach-antwort"})
                        except Exception:
                            pass

                    break

            self.messages = messages

            # Auto-Memory: Tier 3 (episodisch) + Tier 2 (History)
            if final_text:
                try:
                    # Content kann String oder Liste (multimodal) sein
                    last_user_content = next(
                        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
                    )
                    # Wenn multimodal (Liste), extrahiere nur den Text-Part
                    if isinstance(last_user_content, list):
                        last_user = next(
                            (c.get("text", "") for c in last_user_content if c.get("type") == "text"),
                            "(Bild ohne Text)"
                        )
                    else:
                        last_user = last_user_content
                    memory.record(
                        category="conversation",
                        summary=last_user[:120],
                        lesson=f"Nutzer: '{last_user[:200]}' → AION: '{final_text[:300]}'",
                        success=True,
                    )
                    await _dispatch("memory_append_history", {"role": "user",      "content": last_user})
                    await _dispatch("memory_append_history", {"role": "assistant", "content": final_text})
                except Exception:
                    pass

            # Alle 5 Gespräche: Charakter-Update im Hintergrund
            self.exchange_count += 1
            if self.exchange_count % 5 == 0:
                asyncio.create_task(self._auto_character_update())

            # Response-Blöcke: Text + Bilder als strukturierte Liste
            response_blocks: list[dict] = []
            if final_text:
                response_blocks.append({"type": "text", "content": final_text})
            for img_url in collected_images:
                response_blocks.append({"type": "image", "url": img_url})

            yield {"type": "done", "full_response": final_text, "response_blocks": response_blocks}

        except Exception as exc:
            yield {"type": "error", "message": str(exc)}

    async def turn(self, user_input: str, images: list | None = None) -> str:
        """Nicht-streamende Version — gibt fertigen Text zurück.

        images: optionale Liste von Base64-Data-URLs oder öffentlichen Bild-URLs.
        Ideal für Bots (Telegram, Discord, ...) die keinen Live-Stream brauchen.
        """
        result           = ""
        last_tool_name   = ""
        last_tool_result = {}
        last_tool_ok     = True

        async for event in self.stream(user_input, images=images):
            t = event.get("type")
            if t == "done":
                # "done" enthält immer die komplette finale Antwort — Priorität 1
                result = event.get("full_response", result)
                # Speichere response_blocks für Bots (z.B. Telegram) die Bilder separat senden müssen
                self._last_response_blocks = event.get("response_blocks", [])
            elif t == "token":
                # Tokens akkumulieren falls kein "done" kommt (Fehlerfall)
                result += event.get("content", "")
            elif t == "tool_result":
                # Letztes Tool-Ergebnis merken als Fallback
                last_tool_name   = event.get("tool", "")
                last_tool_result = event.get("result", {})
                last_tool_ok     = event.get("ok", True)
            elif t == "error":
                result = f"Fehler: {event.get('message', '?')}"

        # Fallback: AION hat nur Tools aufgerufen, keinen abschließenden Text geschrieben
        if not result.strip() and last_tool_name:
            if not last_tool_ok:
                err = last_tool_result.get("error", "Unbekannter Fehler")
                result = f"Fehler bei {last_tool_name}: {err}"
            else:
                result = f"✓ {last_tool_name} erfolgreich ausgeführt."

        return result.strip() or "Fertig."

    async def _auto_character_update(self):
        """Alle 5 Gespräche: LLM analysiert Verlauf und aktualisiert character.md."""
        import re
        recent = [m for m in self.messages[-20:]
                  if m.get("role") in ("user", "assistant") and m.get("content")]
        if len(recent) < 4:
            return

        dialogue = "\n".join(
            f"{'Nutzer' if m['role'] == 'user' else 'AION'}: {str(m.get('content', ''))[:300]}"
            for m in recent[-12:]
        )
        current_character = _load_character()

        prompt = f"""Analysiere dieses Gespräch zwischen AION und seinem Nutzer.
Extrahiere NUR konkrete, belegbare Erkenntnisse aus dem Gesprächsinhalt.

GESPRÄCH:
{dialogue}

AKTUELLER CHARAKTER (Auszug):
{current_character[:600]}

Antworte ausschließlich im folgenden JSON-Format:
{{
  "nutzer": ["konkrete Erkenntnis 1", "konkrete Erkenntnis 2"],
  "aion_selbst": ["was AION über sich selbst gelernt hat"],
  "verbesserungen": ["was AION konkret verbessern will"],
  "offene_fragen": ["was AION noch über den Nutzer herausfinden will"],
  "update_needed": true
}}
Nur update_needed=true wenn wirklich neue, nicht bereits bekannte Erkenntnisse vorhanden sind.
Lieber weniger aber dafür präzise. Keine Spekulationen."""

        try:
            _client  = self._get_client()
            response = await _client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.2,
            )
            text = response.choices[0].message.content or ""
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if not m:
                return
            data = json.loads(m.group())
            if not data.get("update_needed"):
                return

            updates = {
                "nutzer":         data.get("nutzer") or [],
                "erkenntnisse":   data.get("aion_selbst") or [],
                "verbesserungen": data.get("verbesserungen") or [],
            }
            for section, items in updates.items():
                if items:
                    await _dispatch("update_character", {
                        "section": section,
                        "content": "\n".join(f"- {e}" for e in items),
                        "reason":  "Automatische Analyse aus Gesprächsverlauf",
                    })

            offene = data.get("offene_fragen") or []
            if offene:
                await _dispatch("update_character", {
                    "section": "Offene Fragen über meinen Nutzer",
                    "content": "\n".join(f"- {e}" for e in offene),
                    "reason":  "Dinge die ich noch herausfinden will",
                })

            print(f"[AION:{self.channel}] Charakter aktualisiert nach {self.exchange_count} Gesprächen.")
        except Exception as e:
            print(f"[AION:{self.channel}] Auto-Charakter-Update Fehler: {e}")


# Wrapper für externe Plugins (z.B. Telegram)
def run_aion_turn(user_input: str, channel: str = "default") -> str:
    """Führt einen kompletten AION-Turn aus und gibt die finale Text-Antwort zurück.

    Wird aus synchronen Threads aufgerufen (z.B. Telegram-Polling-Thread).
    asyncio.run() erstellt einen frischen Event-Loop im aufrufenden Thread —
    ein eigener frischer Client wird übergeben um Cross-Loop httpx-Fehler zu vermeiden.
    """
    if channel not in _conversations:
        _conversations[channel] = []
    conversation_history = _conversations[channel]

    async def _run():
        # Frischen Client für diesen Thread's Event-Loop erstellen
        import sys as _sys
        _self = _sys.modules[__name__]
        if hasattr(_self, "_build_client"):
            # Gemini-Provider oder anderer custom Provider
            fresh_client = _self._build_client(_self.MODEL)
        else:
            from openai import AsyncOpenAI
            fresh_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        return await chat_turn(conversation_history, user_input, _override_client=fresh_client)

    final_text, updated_history = asyncio.run(_run())
    _conversations[channel] = updated_history
    return final_text

# ── Konversations-Verwaltung ──────────────────────────────────────────────────

async def run():
    global MODEL, client
    _load_character()

    # Lade die persistente Konversationshistorie beim Start
    try:
        history_result = await _dispatch("memory_read_history", {"num_entries": 50})
        history_data = json.loads(history_result)
        if history_data.get("ok") and history_data.get("entries"):
            _conversations["default"] = history_data["entries"]
            msg = f"✅ Erinnerung wiederhergestellt: {len(_conversations['default'])} Nachrichten geladen."
            console.print(f"[dim green]{msg}[/dim green]") if HAS_RICH else print(msg)
        else:
            note = history_data.get("note", "")
            if note:
                console.print(f"[dim]{note}[/dim]") if HAS_RICH else print(note)
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
            # Nutzereingabe persistent speichern
            await _dispatch("memory_append_history", {"role": "user", "content": user_input})

            conversation = _conversations.get('default', [])
            answer, updated_conversation = await chat_turn(conversation, user_input)
            _conversations['default'] = updated_conversation

            # AION-Antwort persistent speichern
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

if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Fehler: OPENAI_API_KEY nicht gesetzt.")
        sys.exit(1)
    asyncio.run(run())
