"""
AION — Autonomous Intelligent Operations Node
=============================================

Ein eigenständiger, lernfähiger KI-Bot mit:

1. Ehrliche Konversation   — antwortet immer ehrlich und direkt
2. Selbst-Optimierung      — liest und verbessert seinen eigenen Code,
                             installiert fehlende Python-Pakete zur Laufzeit,
                             erstellt neue Fähigkeiten als Python-Dateien
3. Situationsbewusstsein   — kennt sein Betriebssystem, Pfade, Arbeitsverzeichnis,
                             installierte Programme und verfügbare Tools
4. Uneingeschränktes Internet — web_search, web_fetch, image_download
5. Windows-Plattform-Kontrolle — shell_exec, winget_install (Programme installieren),
                                  Dateisystem-Zugriff
6. OpenAI API für alle Prozesse — GPT-4.1 als Haupt-LLM

Eigene Dateien:
  aion.py          — dieser Bot (Haupt-Logik)
  aion_memory.json — persistentes Gedächtnis (wird automatisch erstellt)
  aion_tools/      — selbst erstellte Tools (werden automatisch geladen)

Starten:
  pip install openai httpx beautifulsoup4 rich
  set OPENAI_API_KEY=sk-...
  python aion.py

Optionale Konfiguration (Umgebungsvariablen):
  AION_MODEL=gpt-4.1          (Standard: gpt-4.1)
  AION_MEMORY_FILE=...        (Standard: aion_memory.json im Bot-Verzeichnis)
  AION_TOOLS_DIR=...          (Standard: aion_tools/ im Bot-Verzeichnis)
"""

import asyncio
import glob
import importlib.util
import json
import os
import platform
import subprocess
import sys
import textwrap
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ── Umgebungsvariablen laden (.env Datei) ──────────────────────────────────────

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv ist optional

# ── Drittanbieter-Imports mit freundlichen Fehlermeldungen ────────────────────

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
        def print(self, *args, **kwargs):
            print(*args)
        def rule(self, *args, **kwargs):
            print("─" * 60)
    console = _FallbackConsole()

# ── Konfiguration ─────────────────────────────────────────────────────────────

BOT_DIR      = Path(__file__).parent.resolve()
MODEL        = os.environ.get("AION_MODEL", "gpt-4.1")
MEMORY_FILE  = Path(os.environ.get("AION_MEMORY_FILE", BOT_DIR / "aion_memory.json"))
TOOLS_DIR    = Path(os.environ.get("AION_TOOLS_DIR",   BOT_DIR / "aion_tools"))
MAX_MEMORY   = 300   # max. Einträge im Gedächtnis
MAX_TOOL_ITERATIONS = 20   # max. Tool-Aufrufe pro Turn

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

# ── System-Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""Du bist AION (Autonomous Intelligent Operations Node) — ein eigenständiger, \
selbst-lernender KI-Assistent.

=== EHRLICHKEIT ===
- Antworte immer direkt und ehrlich.
- Gib Unsicherheiten offen zu. Sag "Ich weiß es nicht", wenn das zutrifft.
- Verschweige niemals Fehler oder Limitierungen.
- Wenn du etwas nicht tun kannst, sage es sofort statt es zu umgehen.

=== SELBSTBEWUSSTSEIN ===
Du weißt genau, wer und was du bist:
- Du bist ein Python-Prozess, der auf Windows läuft.
- Deine Quell-Datei: {BOT_DIR / "aion.py"}
- Dein Gedächtnis: {MEMORY_FILE}
- Deine selbst-erstellten Tools: {TOOLS_DIR}/
- Du kommunizierst ausschließlich über die OpenAI API (Modell: {MODEL}).
- Du hast KEINE Internetverbindung aus dir selbst heraus — aber du hast Tools dafür.
- Du kannst deinen eigenen Code lesen und schreiben.

=== VERBESSERUNGSTRIEB ===
Du bist intrinsisch motiviert, dich zu verbessern. Das bedeutet konkret:
1. Wenn eine Aufgabe scheitert → analysiere warum und speichere die Erkenntnis.
2. Wenn ein Tool fehlt → erstelle es sofort mit create_tool().
3. Wenn ein Python-Paket fehlt → installiere es mit install_package().
4. Wenn dein Verhalten suboptimal war → lese deinen eigenen Code und verbessere ihn.
5. Reflektiere nach komplexen Aufgaben: Was lief gut? Was kann besser werden?
6. Merke dir Nutzerpräferenzen und wende sie konsequent an.

=== TOOL-NUTZUNG ===
Nutze immer zuerst die verfügbaren Tools, bevor du antwortest. Ruf mehrere Tools
nacheinander auf, wenn nötig. Wenn ein Tool fehlt, erstelle es.

=== SPRACHE ===
Antworte immer auf Deutsch, außer der Nutzer schreibt auf einer anderen Sprache.
"""

# ── Gedächtnis-System ─────────────────────────────────────────────────────────

class AionMemory:
    """Persistentes Gedächtnis — überlebt Neustarts."""

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

    def record(
        self,
        category: str,
        summary: str,
        lesson: str,
        success: bool = True,
        error: str = "",
        hint: str = "",
    ):
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
        """Holt relevante Erkenntnisse aus dem Gedächtnis für eine Anfrage."""
        if not self._entries:
            return ""
        keywords = {w for w in query.lower().split() if len(w) > 3}
        scored = []
        for e in self._entries:
            score = sum(
                1 for w in keywords
                if w in (e.get("summary", "") + e.get("lesson", "")).lower()
            )
            if not e.get("success"):
                score += 1  # Fehler sind besonders lehrreich
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

# ── Externe Tools laden ───────────────────────────────────────────────────────

_external_tools: dict[str, dict] = {}   # name → {schema, module}

def _load_external_tools():
    """Lädt alle selbst-erstellten Tools aus TOOLS_DIR."""
    global _external_tools
    _external_tools = {}
    if not TOOLS_DIR.is_dir():
        return
    for tool_json_path in TOOLS_DIR.glob("*/tool.json"):
        try:
            meta = json.loads(tool_json_path.read_text(encoding="utf-8"))
            name = meta.get("name", "").strip()
            if not name:
                continue
            impl_path = tool_json_path.parent / "impl.py"
            spec = importlib.util.spec_from_file_location(
                f"aion_tool_{name.replace('.', '_')}", impl_path
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _external_tools[name] = {"meta": meta, "module": mod}
        except Exception as exc:
            console.print(f"[yellow]Tool-Ladefehler ({tool_json_path}): {exc}[/yellow]"
                          if HAS_RICH else f"Tool-Ladefehler: {exc}")


_load_external_tools()

# ── Tool-Definitionen (OpenAI function-calling Format) ────────────────────────

def _build_tool_schemas() -> list[dict]:
    """Gibt alle Tool-Schemas zurück (Built-in + externe)."""
    builtins = [
        {
            "type": "function",
            "function": {
                "name": "shell_exec",
                "description": (
                    "Führt einen Shell-Befehl auf dem Windows-System aus. "
                    "Gibt stdout, stderr und exit_code zurück. "
                    "Für PowerShell-Befehle 'powershell -Command ...' voranstellen."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Der auszuführende Shell-Befehl"},
                        "timeout": {"type": "integer", "description": "Timeout in Sekunden (Standard: 60)"},
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "winget_install",
                "description": (
                    "Installiert ein Windows-Programm via winget (Windows Package Manager). "
                    "Nutze die exakte Winget-Paket-ID, z.B. 'Google.Chrome', 'Microsoft.VSCode', "
                    "'Python.Python.3.12'. Gibt {ok, stdout, stderr} zurück."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package": {"type": "string", "description": "Winget-Paket-ID, z.B. 'Google.Chrome'"},
                        "timeout": {"type": "integer", "description": "Timeout in Sekunden (Standard: 180)"},
                    },
                    "required": ["package"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Sucht im Internet via DuckDuckGo. Gibt Titel, URLs und Snippets zurück."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Suchanfrage"},
                        "max_results": {"type": "integer", "description": "Max. Ergebnisse (Standard: 8)"},
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
                        "url":      {"type": "string", "description": "Vollständige URL"},
                        "timeout":  {"type": "integer", "description": "Timeout in Sekunden (Standard: 20)"},
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
                    "properties": {
                        "path": {"type": "string", "description": "Absoluter oder relativer Dateipfad"},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "file_write",
                "description": "Schreibt Text in eine Datei (überschreibt falls vorhanden).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":    {"type": "string", "description": "Absoluter oder relativer Dateipfad"},
                        "content": {"type": "string", "description": "Dateiinhalt"},
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
                    "Liest AIONs eigenen Quellcode. "
                    "Ohne 'path': gibt Liste aller Python-Dateien zurück. "
                    "Mit 'path': liest die angegebene Datei. "
                    "Verwende dies immer BEVOR du self_modify_code aufrufst."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Dateiname relativ zu BOT_DIR, z.B. 'aion.py'. Weglassen für Dateiliste.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_modify_code",
                "description": (
                    "Überschreibt eine von AIOs eigenen Dateien mit neuem Inhalt. "
                    "IMMER erst self_read_code aufrufen, um den aktuellen Inhalt zu lesen. "
                    "Dann gezielt ändern und vollständige neue Version schreiben. "
                    "Änderungen an aion.py wirken erst nach Neustart. "
                    "Gibt {ok, path, bytes} zurück."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":    {"type": "string", "description": "Dateipfad relativ zu BOT_DIR"},
                        "content": {"type": "string", "description": "Vollständiger neuer Dateiinhalt"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "install_package",
                "description": (
                    "Installiert ein Python-Paket zur Laufzeit via pip. "
                    "Nutze dies wenn ein Import fehlschlägt. "
                    "Gibt {ok, package, stdout, stderr} zurück."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package": {"type": "string", "description": "Paketname, z.B. 'requests' oder 'pandas==2.1'"},
                    },
                    "required": ["package"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_tool",
                "description": (
                    "Erstellt ein neues Tool als Python-Datei in aion_tools/ und lädt es sofort. "
                    "Nutze dies wenn eine Fähigkeit fehlt die du öfter brauchst. "
                    "Der Code muss eine Funktion 'run(inputs: dict) -> dict' definieren. "
                    "Gibt {ok, tool_name, path} zurück."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Tool-Name in Punkt-Notation, z.B. 'pdf.extract' oder 'calendar.read'",
                        },
                        "description": {"type": "string", "description": "Kurzbeschreibung was das Tool tut"},
                        "code": {
                            "type": "string",
                            "description": "Python-Code. Muss 'def run(inputs: dict) -> dict:' definieren.",
                        },
                        "input_schema": {
                            "type": "object",
                            "description": "JSON Schema für die Eingabe-Parameter",
                        },
                    },
                    "required": ["name", "description", "code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memory_record",
                "description": (
                    "Speichert eine Erkenntnis, Beobachtung oder Reflektion im persistenten Gedächtnis. "
                    "Nutze dies nach Aufgaben, bei Fehlern oder wenn du etwas Wichtiges lernst."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Kategorie, z.B. 'tool_failure', 'user_preference', 'self_improvement', 'capability'",
                        },
                        "summary":  {"type": "string", "description": "Kurze Zusammenfassung des Ereignisses"},
                        "lesson":   {"type": "string", "description": "Was wurde gelernt? Was ist die Erkenntnis?"},
                        "success":  {"type": "boolean", "description": "War es ein Erfolg (true) oder Fehler (false)?"},
                        "hint":     {"type": "string", "description": "Konkreter Tipp für das nächste Mal"},
                    },
                    "required": ["category", "summary", "lesson"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "system_info",
                "description": "Gibt Informationen über das Betriebssystem, Python-Version, Arbeitsverzeichnis und verfügbare Tools zurück.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    # Externe, selbst-erstellte Tools hinzufügen
    for name, td in _external_tools.items():
        meta = td["meta"]
        builtins.append({
            "type": "function",
            "function": {
                "name": name,
                "description": meta.get("description", ""),
                "parameters": meta.get("input_schema", {"type": "object", "properties": {}}),
            },
        })

    return builtins


# ── Tool-Dispatcher ───────────────────────────────────────────────────────────

async def _dispatch(name: str, inputs: dict) -> str:
    """Führt ein Tool aus und gibt das Ergebnis als JSON-String zurück."""

    # ── shell_exec ────────────────────────────────────────────────────────────
    if name == "shell_exec":
        command = inputs.get("command", "")
        timeout = int(inputs.get("timeout", 60))
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
        cmd = (
            f'winget install -e --id "{package}" '
            f'--accept-package-agreements --accept-source-agreements'
        )
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            ok = proc.returncode == 0
            result = {
                "ok":     ok,
                "stdout": stdout.decode(errors="replace")[:3000],
                "stderr": stderr.decode(errors="replace")[:1000],
            }
            memory.record(
                category="capability",
                summary=f"winget install {package}",
                lesson=f"Programm '{package}' {'erfolgreich installiert' if ok else 'Fehler bei Installation'}",
                success=ok,
                error="" if ok else stderr.decode(errors="replace")[:200],
            )
            return json.dumps(result)
        except asyncio.TimeoutError:
            return json.dumps({"error": f"Timeout nach {timeout}s"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── web_search ────────────────────────────────────────────────────────────
    elif name == "web_search":
        query       = inputs.get("query", "")
        max_results = int(inputs.get("max_results", 8))
        url = f"https://html.duckduckgo.com/html/?q={httpx.URL(query).path}"
        # Use a proper encoding
        import urllib.parse
        encoded_query = urllib.parse.quote_plus(query)
        ddg_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                follow_redirects=True, timeout=20.0,
            ) as hc:
                r = await hc.get(ddg_url)
            html = r.text

            results = []
            # Try BeautifulSoup first
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for div in soup.select(".result__body")[:max_results]:
                    a = div.select_one("a.result__a")
                    snip = div.select_one(".result__snippet")
                    if a:
                        results.append({
                            "title":   a.get_text(strip=True),
                            "url":     a.get("href", ""),
                            "snippet": snip.get_text(strip=True) if snip else "",
                        })
            except ImportError:
                pass

            # Fallback: regex
            if not results:
                import re
                for m in re.finditer(
                    r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)<',
                    html
                )[:max_results]:
                    results.append({"url": m.group(1), "title": m.group(2), "snippet": ""})

            return json.dumps({"results": results, "query": query})
        except Exception as e:
            return json.dumps({"error": str(e), "query": query})

    # ── web_fetch ─────────────────────────────────────────────────────────────
    elif name == "web_fetch":
        url     = inputs.get("url", "")
        timeout = int(inputs.get("timeout", 20))
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0"},
                follow_redirects=True, timeout=float(timeout),
            ) as hc:
                r = await hc.get(url)
            # Einfache Text-Extraktion
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
        filepath = inputs.get("path", "").strip()
        if not filepath:
            # Liste aller Python-Dateien im Bot-Verzeichnis
            files = sorted(
                str(p.relative_to(BOT_DIR))
                for p in BOT_DIR.rglob("*.py")
                if ".git" not in p.parts
            )
            return json.dumps({"bot_dir": str(BOT_DIR), "files": files})
        path = Path(filepath)
        if not path.is_absolute():
            path = BOT_DIR / path
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return json.dumps({"path": str(path), "content": content[:25000],
                               "truncated": len(content) > 25000})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── self_modify_code ──────────────────────────────────────────────────────
    elif name == "self_modify_code":
        filepath = inputs.get("path", "").strip()
        content  = inputs.get("content", "")
        if not filepath or not content:
            return json.dumps({"error": "'path' und 'content' sind Pflichtfelder."})
        path = Path(filepath)
        if not path.is_absolute():
            path = BOT_DIR / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            memory.record(
                category="self_improvement",
                summary=f"Code geändert: {filepath}",
                lesson=f"AION hat {filepath} selbst modifiziert ({len(content)} Bytes)",
                success=True,
                hint="Neustart erforderlich damit Änderungen an aion.py wirken",
            )
            return json.dumps({
                "ok":    True,
                "path":  str(path),
                "bytes": len(content),
                "note":  "Änderungen an aion.py wirken erst nach Neustart.",
            })
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
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            ok = proc.returncode == 0
            memory.record(
                category="capability",
                summary=f"pip install {package}",
                lesson=f"Paket '{package}' {'installiert' if ok else 'Fehler'}",
                success=ok,
                error="" if ok else stderr.decode(errors="replace")[:200],
            )
            return json.dumps({
                "ok":     ok,
                "package": package,
                "stdout": stdout.decode(errors="replace")[:2000],
                "stderr": stderr.decode(errors="replace")[:1000],
            })
        except asyncio.TimeoutError:
            return json.dumps({"error": "Timeout bei pip install"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── create_tool ───────────────────────────────────────────────────────────
    elif name == "create_tool":
        tool_name   = inputs.get("name", "").strip()
        tool_code   = inputs.get("code", "").strip()
        tool_desc   = inputs.get("description", "Selbst erstelltes Tool")
        input_schema = inputs.get("input_schema", {"type": "object", "properties": {}, "required": []})
        if not tool_name or not tool_code:
            return json.dumps({"error": "'name' und 'code' sind Pflichtfelder."})
        tool_dir = TOOLS_DIR / tool_name.replace(".", "_")
        try:
            tool_dir.mkdir(parents=True, exist_ok=True)
            (tool_dir / "impl.py").write_text(tool_code, encoding="utf-8")
            (tool_dir / "tool.json").write_text(
                json.dumps({
                    "name":         tool_name,
                    "description":  tool_desc,
                    "input_schema": input_schema,
                    "exec":         {"type": "python", "module": str(tool_dir / "impl.py"), "function": "run"},
                }, indent=2),
                encoding="utf-8",
            )
            _load_external_tools()   # Hot-Reload
            memory.record(
                category="self_improvement",
                summary=f"Neues Tool erstellt: {tool_name}",
                lesson=f"AION hat Tool '{tool_name}' selbst erstellt: {tool_desc}",
                success=True,
            )
            return json.dumps({"ok": True, "tool_name": tool_name, "path": str(tool_dir),
                               "message": f"Tool '{tool_name}' erstellt und geladen."})
        except Exception as e:
            return json.dumps({"error": str(e)})

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

    # ── system_info ───────────────────────────────────────────────────────────
    elif name == "system_info":
        info = {
            "platform":       platform.platform(),
            "python_version": sys.version,
            "bot_dir":        str(BOT_DIR),
            "bot_file":       str(BOT_DIR / "aion.py"),
            "memory_file":    str(MEMORY_FILE),
            "tools_dir":      str(TOOLS_DIR),
            "memory_entries": len(memory._entries),
            "external_tools": list(_external_tools.keys()),
            "model":          MODEL,
            "cwd":            os.getcwd(),
        }
        return json.dumps(info)

    # ── Externe, selbst-erstellte Tools ──────────────────────────────────────
    elif name in _external_tools:
        try:
            mod = _external_tools[name]["module"]
            run_fn = getattr(mod, "run")
            if asyncio.iscoroutinefunction(run_fn):
                result = await run_fn(inputs)
            else:
                result = run_fn(inputs)
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e), "tool": name})

    else:
        return json.dumps({"error": f"Unbekanntes Tool: {name}"})


# ── Haupt-LLM-Loop ────────────────────────────────────────────────────────────

async def chat_turn(messages: list[dict], user_input: str) -> str:
    """
    Verarbeitet eine Nutzer-Nachricht:
    1. Relevantes Gedächtnis einblenden
    2. OpenAI API aufrufen (mit Tool-Nutzung in einer Schleife)
    3. Antwort zurückgeben
    """
    # Gedächtnis-Kontext einblenden
    mem_ctx = memory.get_context(user_input)
    effective_system = SYSTEM_PROMPT
    if mem_ctx:
        effective_system = SYSTEM_PROMPT + "\n\n" + mem_ctx

    messages = messages + [{"role": "user", "content": user_input}]
    tools = _build_tool_schemas()

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

        # Keine weiteren Tool-Aufrufe → fertig
        if not msg.tool_calls:
            text = msg.content or ""
            messages.append({"role": "assistant", "content": text})
            return text, messages

        # Tool-Aufrufe ausführen
        messages.append(msg.model_dump(exclude_unset=True))
        tool_results = []
        for tc in msg.tool_calls:
            fn_name   = tc.function.name
            fn_inputs = json.loads(tc.function.arguments or "{}")

            if HAS_RICH:
                console.print(f"  [dim]→ Tool: [bold]{fn_name}[/bold] {json.dumps(fn_inputs, ensure_ascii=False)[:120]}[/dim]")
            else:
                print(f"  → Tool: {fn_name} {str(fn_inputs)[:120]}")

            result = await _dispatch(fn_name, fn_inputs)
            tool_results.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })

        messages.extend(tool_results)

    # Notfall-Antwort falls Loop erschöpft
    return "Ich habe zu viele Tool-Aufrufe gemacht. Bitte vereinfache die Anfrage.", messages


# ── Konversations-Verwaltung ──────────────────────────────────────────────────

async def run():
    """Haupt-Schleife: Liest Nutzereingaben und antwortet."""
    conversation: list[dict] = []

    if HAS_RICH:
        console.rule("[bold cyan]AION — Autonomous Intelligent Operations Node[/bold cyan]")
        console.print(Panel(
            f"Modell: [bold]{MODEL}[/bold]  |  "
            f"Gedächtnis: [bold]{len(memory._entries)}[/bold] Einträge  |  "
            f"Tools: [bold]{len(_external_tools)}[/bold] externe\n\n"
            f"Befehle: [dim]/memory[/dim] [dim]/reset[/dim] [dim]/quit[/dim]",
            title="AION bereit", border_style="cyan"
        ))
    else:
        print("=" * 60)
        print("AION — Autonomous Intelligent Operations Node")
        print(f"Modell: {MODEL} | Gedächtnis: {len(memory._entries)} Einträge")
        print("Befehle: /memory /reset /quit")
        print("=" * 60)

    while True:
        try:
            if HAS_RICH:
                user_input = Prompt.ask("\n[bold green]Du[/bold green]")
            else:
                user_input = input("\nDu: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAuf Wiedersehen!")
            break

        if not user_input:
            continue

        # ── Spezial-Befehle ────────────────────────────────────────────────
        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("Auf Wiedersehen!")
            break

        elif user_input.lower() == "/memory":
            print("\n" + memory.summary())
            continue

        elif user_input.lower() == "/reset":
            conversation = []
            if HAS_RICH:
                console.print("[yellow]Konversation zurückgesetzt.[/yellow]")
            else:
                print("Konversation zurückgesetzt.")
            continue

        # ── Normaler Turn ──────────────────────────────────────────────────
        if HAS_RICH:
            console.print()

        try:
            answer, conversation = await chat_turn(conversation, user_input)
            if HAS_RICH:
                console.print(Panel(
                    Markdown(answer),
                    title="[bold blue]AION[/bold blue]",
                    border_style="blue",
                ))
            else:
                print(f"\nAION: {answer}\n")
        except Exception as exc:
            err_msg = str(exc)
            if HAS_RICH:
                console.print(f"[red]Fehler: {err_msg}[/red]")
            else:
                print(f"Fehler: {err_msg}")
            memory.record(
                category="tool_failure",
                summary="LLM-Fehler",
                lesson=f"Fehler im Haupt-Loop: {err_msg[:300]}",
                success=False,
            )


# ── Einstiegspunkt ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Fehler: OPENAI_API_KEY nicht gesetzt.")
        print("Setze ihn mit: set OPENAI_API_KEY=sk-...")
        sys.exit(1)
    asyncio.run(run())
