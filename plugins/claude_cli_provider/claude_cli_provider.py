"""
AION Plugin: Claude CLI Provider
==================================
Nutzt die installierte claude CLI (Claude Code) für hochwertige Aufgaben —
kein API-Key nötig, läuft über dein bestehendes Claude-Abo.

Workflow:
  AION (Gemini/GPT) koordiniert → liest Fileen → übergibt an Claude →
  Claude denkt nach → AION schreibt Ergebnis zurück

Setup:
  1. Claude Code installieren: https://claude.ai/download
  2. Mit Abo anmelden: claude login (einmalig im Terminal)
  3. Verifizieren: claude --print "Hallo" → gibt Antwort aus

Task-Routing (optional, in config.json):
  "task_routing": {
    "coding":   "claude-opus-4-6",
    "browsing": "gemini-2.5-flash",
    "default":  "gemini-2.5-flash"
  }

AION folgt dann automatisch den Routing-Regeln aus rules.md.
"""

import json
import subprocess
import sys

# ── claude CLI finden ─────────────────────────────────────────────────────────

def _find_claude() -> "str | None":
    """Sucht die claude CLI — delegiert an config_store.find_claude_bin()."""
    from config_store import find_claude_bin
    return find_claude_bin()


def _claude_authenticated() -> bool:
    """Schnelltest: ist claude CLI angemeldet?"""
    claude_bin = _find_claude()
    if not claude_bin:
        return False
    try:
        r = subprocess.run(
            [claude_bin, "--print", "--model", "claude-haiku-4-5-20251001", "ping"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        return r.returncode == 0
    except Exception:
        return False


def claude_cli_login(**_) -> dict:
    """
    Startet 'claude login' — öffnet den Browser für die Anmeldung mit dem Claude-Abo.
    Kein API-Key nötig. Nach dem Login im Browser ist ask_claude sofort verfügbar.
    """
    claude_bin = _find_claude()

    # Noch not installed → npm install
    if not claude_bin:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            return {
                "ok": False,
                "error": (
                    "npm nicht gefunden. Node.js installieren: https://nodejs.org\n"
                    "Danach: npm install -g @anthropic-ai/claude-code && claude login"
                ),
            }
        print("[claude_cli] Installiere @anthropic-ai/claude-code via npm...")
        r = subprocess.run(
            [npm, "install", "-g", "@anthropic-ai/claude-code"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            return {"ok": False, "error": f"npm install fehlgeschlagen: {r.stderr[:300]}"}
        claude_bin = _find_claude()
        if not claude_bin:
            return {"ok": False, "error": "Nach Installation nicht gefunden — Terminal neu starten."}

    # Bereits angemeldet?
    if _claude_authenticated():
        return {"ok": True, "message": "Claude CLI ist bereits angemeldet. ask_claude ist sofort nutzbar."}

    # Browser für Login öffnen
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                [claude_bin, "login"],
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            subprocess.Popen([claude_bin, "login"])
        return {
            "ok": True,
            "message": (
                "Browser wurde geöffnet. Melde dich mit deinem Claude-Konto an.\n"
                "Nach dem Login kannst du ask_claude sofort verwenden.\n"
                "Status prüfen: claude_cli_status()"
            ),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def claude_cli_status(**_) -> dict:
    """Checks ob claude CLI installiert und angemeldet ist."""
    claude_bin = _find_claude()
    if not claude_bin:
        return {
            "ok": False,
            "installed": False,
            "authenticated": False,
            "message": "Claude CLI not installed. claude_cli_login() aufrufen.",
        }
    authed = _claude_authenticated()
    return {
        "ok": True,
        "installed": True,
        "authenticated": authed,
        "path": claude_bin,
        "message": "Angemeldet — ask_claude ist nutzbar." if authed else "Nicht angemeldet — claude_cli_login() aufrufen.",
    }


def _load_task_routing() -> dict:
    """Reads task_routing aus config.json."""
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("task_routing", {})
    except Exception:
        return {}


# ── Haupt-Tool ────────────────────────────────────────────────────────────────

def ask_claude(
    prompt: str,
    model: str = "",
    context_files: list = None,
    task_type: str = "",
    **_,
) -> dict:
    """
    Sendet eine Anfrage an Claude via CLI und gibt die Antwort zurück.

    - prompt: Die Aufgabe/Frage
    - model: z.B. "claude-opus-4-6" (default aus task_routing oder claude-opus-4-6)
    - context_files: Liste von Filepfaden — Inhalt wird automatisch angehängt
    - task_type: "coding" / "review" / "analysis" (optional, für Logging)
    """
    # Vorab-Check: Claude muss angemeldet sein, bevor wir den Prozess starten
    claude_bin = _find_claude()
    if not claude_bin:
        return {
            "ok": False,
            "error": (
                "Claude CLI nicht gefunden — Claude ist nicht konfiguriert. "
                "Bitte Claude Code installieren (https://claude.ai/download) "
                "und einmalig 'claude login' im Terminal ausführen."
            ),
        }
    if not _claude_authenticated():
        return {
            "ok": False,
            "error": (
                "Claude ist nicht angemeldet — kein Claude-Abo verbunden und kein ANTHROPIC_API_KEY hinterlegt. "
                "Bitte 'claude login' im Terminal ausführen oder einen API-Key unter Keys hinterlegen. "
                "ask_claude ist nur mit aktivem Claude-Abo oder konfiguriertem API-Key nutzbar."
            ),
        }

    # Modell aus task_routing ermitteln, falls nicht explizit angegeben
    if not model:
        routing = _load_task_routing()
        model = routing.get(task_type or "coding") or routing.get("default") or "claude-opus-4-6"

    # Fileen an Prompt anhängen
    full_prompt = prompt
    if context_files:
        for path in context_files:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                # Nur erste 30.000 Zeichen pro File (Claude-Kontextlimit beachten)
                if len(content) > 30_000:
                    content = content[:30_000] + "\n\n[... File gekürzt ...]"
                full_prompt += f"\n\n=== File: {path} ===\n{content}\n"
            except Exception as e:
                full_prompt += f"\n[Error beim Lesen von {path}: {e}]\n"

    try:
        result = subprocess.run(
            [claude_bin, "--print", "--model", model, full_prompt],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            err = result.stderr.strip() or f"Exit-Code {result.returncode}"
            # Häufiger Error: nicht angemeldet
            if "login" in err.lower() or "auth" in err.lower() or "token" in err.lower():
                err += "\n→ Tipp: 'claude login' im Terminal ausführen um das Abo zu verknüpfen."
            return {"ok": False, "error": err}

        response = result.stdout.strip()
        if not response:
            return {"ok": False, "error": "Claude gab keine Antwort zurück."}

        return {
            "ok": True,
            "response": response,
            "model": model,
            "chars": len(response),
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timeout (300 Sekunden überschritten)."}
    except FileNotFoundError:
        return {
            "ok": False,
            "error": f"claude CLI nicht ausführbar: {claude_bin}",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_task_routing(**_) -> dict:
    """Zeigt die aktuelle Task-Routing-Configuration."""
    routing = _load_task_routing()
    claude_bin = _find_claude()
    return {
        "ok": True,
        "routing": routing,
        "claude_cli": claude_bin or "nicht gefunden",
        "claude_available": claude_bin is not None,
        "example": {
            "coding":   "claude-opus-4-6   (Standardwert wenn nicht konfiguriert)",
            "browsing": "z.B. gemini-2.5-flash",
            "default":  "Fallback für alle anderen Aufgaben",
        },
    }


def set_task_routing(
    coding: str = "",
    browsing: str = "",
    default: str = "",
    **_,
) -> dict:
    """
    Setzt die Task-Routing-Configuration in config.json.
    Leere Strings = nicht ändern. Verwende 'remove' um einen Eintrag zu löschen.
    """
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        routing = cfg.get("task_routing", {})

        for key, value in [("coding", coding), ("browsing", browsing), ("default", default)]:
            if value == "remove":
                routing.pop(key, None)
            elif value:
                routing[key] = value

        cfg["task_routing"] = routing

        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

        return {"ok": True, "routing": routing, "message": "Task-Routing gespeichert."}

    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Register ──────────────────────────────────────────────────────────────────

def register(api):
    api.register_tool(
        name="ask_claude",
        description=(
            "Sendet eine Aufgabe an Claude (via Claude Code CLI) — nutzt dein Claude-Abo, kein API-Key nötig. "
            "Optimal für: komplexen Code schreiben/refaktorieren, Code-Review, Algorithmen, Architektur-Entscheidungen. "
            "Workflow: 1) file_read() für relevante Fileen, 2) ask_claude(prompt, context_files=[...]), "
            "3) Ergebnis via file_replace_lines() oder file_write() anwenden. "
            "task_type='coding' | 'review' | 'analysis' — steuert das Routing-Modell aus config.json. "
            "HINWEIS: Prüfe task_routing-Configuration via get_task_routing() falls unklar welches Modell."
        ),
        func=ask_claude,
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Die Aufgabe / Frage an Claude. Sei präzise und vollständig.",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Claude-Modell (optional — default aus task_routing). "
                        "Optionen: claude-opus-4-6 (beste Qualität), "
                        "claude-sonnet-4-6 (schnell+gut), claude-haiku-4-5-20251001 (sehr schnell)"
                    ),
                },
                "context_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optionale Filepfade — Inhalt wird automatisch an den Prompt angehängt. "
                        "Example: ['plugins/aion.py', 'config.json']"
                    ),
                },
                "task_type": {
                    "type": "string",
                    "description": "Aufgabentyp für Routing: 'coding', 'review', 'analysis'",
                },
            },
            "required": ["prompt"],
        },
    )

    api.register_tool(
        name="get_task_routing",
        description=(
            "Zeigt die aktuelle Task-Routing-Configuration: welches Modell für welche Aufgabe verwendet wird. "
            "Zeigt auch ob claude CLI verfügbar ist."
        ),
        func=get_task_routing,
        input_schema={"type": "object", "properties": {}, "required": []},
    )

    api.register_tool(
        name="set_task_routing",
        description=(
            "Konfiguriert Task-Routing in config.json: welches Modell für coding/browsing/default verwendet wird. "
            "Example: set_task_routing(coding='claude-opus-4-6', default='gemini-2.5-flash'). "
            "Verwende 'remove' als Wert um einen Eintrag zu löschen."
        ),
        func=set_task_routing,
        input_schema={
            "type": "object",
            "properties": {
                "coding": {
                    "type": "string",
                    "description": "Modell für Code-Aufgaben. Z.B. 'claude-opus-4-6'",
                },
                "browsing": {
                    "type": "string",
                    "description": "Modell für Browser/Web-Aufgaben. Z.B. 'gemini-2.5-flash'",
                },
                "default": {
                    "type": "string",
                    "description": "Standard-Modell für alle anderen Aufgaben.",
                },
            },
            "required": [],
        },
    )

    api.register_tool(
        name="claude_cli_login",
        description=(
            "Startet den Claude-Login — öffnet den Browser zur Anmeldung mit dem Claude-Abo ($20/$200). "
            "Installiert Claude Code CLI automatisch via npm falls noch nicht vorhanden. "
            "Nach dem Login im Browser ist ask_claude sofort nutzbar. "
            "Aufrufen wenn: User sagt 'melde mich bei Claude an', 'Claude Login', 'Claude CLI einrichten'."
        ),
        func=claude_cli_login,
        input_schema={"type": "object", "properties": {}, "required": []},
    )

    api.register_tool(
        name="claude_cli_status",
        description=(
            "Prüft ob Claude CLI installiert und mit dem Claude-Abo angemeldet ist. "
            "Zeigt Pfad zur CLI und ob ask_claude sofort nutzbar ist."
        ),
        func=claude_cli_status,
        input_schema={"type": "object", "properties": {}, "required": []},
    )

    print("[claude_cli_provider] ask_claude, claude_cli_login, claude_cli_status, get/set_task_routing loaded.")

    # Startup-Check
    claude_bin = _find_claude()
    if claude_bin:
        authed = _claude_authenticated()
        status = "logged in" if authed else "NOT logged in (call claude_cli_login)"
        print(f"[claude_cli_provider] claude CLI: {claude_bin} — {status}")
    else:
        print("[claude_cli_provider] claude CLI not found — call claude_cli_login() to set up.")
