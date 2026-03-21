#!/usr/bin/env python3
"""
AION CLI — Interaktive Kommandozeilen-Schnittstelle.

Alternative zu aion_web.py — kein Browser, kein Server.
Einsatz: Server ohne GUI, Automatisierung, ressourcenschonender Betrieb.

Start:
    python aion_cli.py
    start_cli.bat
"""

import asyncio
import sys
import os

# Sicherstellen dass AION-Verzeichnis als Working-Dir gilt
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── Farb-Codes (nur im echten Terminal) ──────────────────────────────────────
_TTY = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text

C_LOGO    = "96;1"  # cyan bold
C_AION    = "96"    # cyan
C_TOOL    = "33"    # yellow
C_THOUGHT = "35"    # purple
C_ERR     = "31"    # red
C_DIM     = "90"    # dunkelgrau
C_BOLD    = "1"     # fett
C_GREEN   = "32"    # grün


BANNER = f"""
{_c(C_LOGO, '  ╔══════════════════════════════════════╗')}
{_c(C_LOGO, '  ║  AION  —  CLI-Modus                  ║')}
{_c(C_LOGO, '  ║  exit / Strg+C zum Beenden           ║')}
{_c(C_LOGO, '  ╚══════════════════════════════════════╝')}
"""


# ── Hauptlogik ────────────────────────────────────────────────────────────────

async def main():
    # AION-Core importieren (lädt Plugins, Memory, Konfiguration)
    print(_c(C_DIM, "  AION wird initialisiert…"), end=" ", flush=True)
    try:
        import aion as _aion
    except ImportError as e:
        print(_c(C_ERR, f"✗ Import-Fehler: {e}"))
        print(_c(C_DIM, "  Starte aus dem AION-Verzeichnis: python aion_cli.py"))
        return

    print(_c(C_GREEN, "✓"))

    # Status anzeigen
    info_parts = []
    if hasattr(_aion, "MODEL"):
        info_parts.append(f"Modell: {_c(C_BOLD, _aion.MODEL)}")
    if hasattr(_aion, "_plugin_tools"):
        info_parts.append(f"Tools: {_c(C_BOLD, str(len(_aion._plugin_tools)))}")
    if info_parts:
        print(_c(C_DIM, "  " + "  |  ".join(info_parts)))
    print()

    # Session erstellen
    session = _aion.AionSession(channel="cli")

    # Neueste Konversationshistorie laden (gibt Kontext)
    try:
        await session.load_history(num_entries=20)
        print(_c(C_DIM, "  Gesprächs-Kontext geladen."))
    except Exception:
        pass

    print()

    # ── Interaktions-Schleife ──────────────────────────────────────────────────
    while True:
        # Eingabe
        try:
            user_input = input(_c(C_BOLD, "Du  › ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print(_c(C_DIM, "\n  Sitzung beendet. Tschüss! 👋"))
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "beenden", "bye", "/exit"):
            print(_c(C_DIM, "\n  Sitzung beendet. Tschüss! 👋"))
            break

        # Interne Befehle
        if user_input.lower() in ("/help", "help"):
            print(_c(C_DIM, """
  Befehle:
    exit / quit      → Sitzung beenden
    /help            → Diese Hilfe
    /clear           → Terminal leeren
    /model           → Aktives Modell anzeigen
"""))
            continue

        if user_input.lower() == "/clear":
            os.system("cls" if os.name == "nt" else "clear")
            continue

        if user_input.lower() == "/model":
            model = getattr(_aion, "MODEL", "?")
            print(_c(C_DIM, f"  Aktives Modell: {_c(C_BOLD, model)}\n"))
            continue

        # ── Antwort streamen ───────────────────────────────────────────────────
        print()
        aion_text_started = False

        try:
            async for event in session.stream(user_input):
                etype = event.get("type")

                if etype == "thought":
                    thought_text = event.get("text", "")
                    trigger      = event.get("trigger", "")
                    # Kompakte Vorschau — erste Zeile
                    preview = thought_text.replace("\n", " ").strip()[:90]
                    trig_str = f"  [{trigger}]" if trigger else ""
                    print(_c(C_THOUGHT, f"  💭 {preview}{trig_str}"))

                elif etype == "token":
                    if not aion_text_started:
                        print(_c(C_AION, "AION › "), end="", flush=True)
                        aion_text_started = True
                    sys.stdout.write(event.get("content", ""))
                    sys.stdout.flush()

                elif etype == "tool_call":
                    tool_name = event.get("tool", "")
                    args      = event.get("args", {})
                    args_str  = str(args)
                    if len(args_str) > 70:
                        args_str = args_str[:70] + "…"
                    print(_c(C_TOOL, f"  ⚙  {tool_name}({args_str})"), end="  ", flush=True)

                elif etype == "tool_result":
                    ok         = event.get("ok", True)
                    result     = event.get("result", {})
                    result_str = str(result)
                    if len(result_str) > 100:
                        result_str = result_str[:100] + "…"
                    status = "✓" if ok else "✗"
                    color  = C_DIM if ok else C_ERR
                    print(_c(color, f"→ {status} {result_str}"))

                elif etype == "done":
                    if aion_text_started:
                        print()  # Zeilenumbruch nach Stream-Text
                    break

                elif etype == "error":
                    if aion_text_started:
                        print()
                    print(_c(C_ERR, f"  ✗ Fehler: {event.get('message', '?')}"))
                    break

        except KeyboardInterrupt:
            if aion_text_started:
                print()
            print(_c(C_DIM, "  (Unterbrochen)"))

        except Exception as e:
            if aion_text_started:
                print()
            print(_c(C_ERR, f"  ✗ Fehler: {e}"))

        print()


if __name__ == "__main__":
    print(BANNER)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(_c(C_DIM, "\n  Sitzung beendet."))
