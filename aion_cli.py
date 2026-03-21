#!/usr/bin/env python3
"""
AION CLI — Interaktive Kommandozeilen-Schnittstelle.

Start:  python aion_cli.py   |   start.bat  →  Modus [2]
"""
import asyncio
import os
import sys
import threading
import time

# UTF-8 auf Windows aktivieren
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── ANSI Farben ───────────────────────────────────────────────────────────────
_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text

C_LOGO    = "96;1"
C_AION    = "96"
C_TOOL    = "33"
C_THOUGHT = "35"
C_ERR     = "91"
C_DIM     = "90"
C_BOLD    = "1"
C_WHITE   = "97"
C_GREEN   = "92"

# ── Box-Zeichner ──────────────────────────────────────────────────────────────
_BW = 42   # sichtbare Inhaltsbreite zwischen ║  ...  ║

def _row(label: str, value: str, lc: str = "90", vc: str = "97") -> str:
    """Erzeugt ║  LABEL   VALUE   ║ (sichtbare Längen korrekt berechnet)."""
    lbl = f"{label:<11}"
    val = str(value)
    used = 11 + 2 + len(val)
    if used > _BW:
        val = val[:_BW - 14] + "…"
        used = _BW
    pad = " " * (_BW - used)
    c = f"{_c(lc, lbl)}  {_c(vc, val)}{pad}"
    return f"  {_c(C_LOGO, '║')}  {c}  {_c(C_LOGO, '║')}"

def _row_plain(text: str, tc: str = "90") -> str:
    """Erzeugt ║  TEXT   ║ (volle Breite, zentriert od. links)."""
    vis = len(text)
    if vis > _BW:
        text = text[:_BW - 1] + "…"
        vis  = _BW
    pad = " " * (_BW - vis)
    return f"  {_c(C_LOGO, '║')}  {_c(tc, text)}{pad}  {_c(C_LOGO, '║')}"

def _box_top(title: str) -> list[str]:
    pad = " " * max(0, _BW - len(title))
    return [
        f"  {_c(C_LOGO, '╔' + '═' * (_BW + 4) + '╗')}",
        f"  {_c(C_LOGO, '║')}  {_c('97;1', title)}{pad}  {_c(C_LOGO, '║')}",
        f"  {_c(C_LOGO, '╠' + '═' * (_BW + 4) + '╣')}",
    ]

def _box_sep() -> str:
    return f"  {_c(C_LOGO, '╠' + '═' * (_BW + 4) + '╣')}"

def _box_empty() -> str:
    return f"  {_c(C_LOGO, '║')}  {' ' * _BW}  {_c(C_LOGO, '║')}"

def _box_bot() -> str:
    return f"  {_c(C_LOGO, '╚' + '═' * (_BW + 4) + '╝')}"


# ── Stats-Box ─────────────────────────────────────────────────────────────────
def print_stats(aion_module) -> None:
    model       = getattr(aion_module, "MODEL", "?")
    tools_count = len(getattr(aion_module, "_plugin_tools", {}))

    mem_str = "?"
    try:
        mem = getattr(aion_module, "memory", None)
        if mem and hasattr(mem, "_entries"):
            mem_str = f"{len(mem._entries)} Einträge"
    except Exception:
        pass

    todo_str = "?"
    try:
        from pathlib import Path
        tf = Path(__file__).parent / "todo.md"
        if tf.exists():
            n = sum(1 for l in tf.read_text(encoding="utf-8").splitlines()
                    if l.strip().startswith("- [ ]"))
            todo_str = f"{n} offen" if n else _c(C_GREEN, "alle erledigt ✓")
    except Exception:
        pass

    for line in _box_top("AION  ·  CLI"):
        print(line)
    print(_row("Modell",  model,       "90", C_AION))
    print(_row("Tools",   tools_count, "90", C_WHITE))
    print(_row("Memory",  mem_str,     "90", C_WHITE))
    print(_row("Todos",   todo_str,    "90", C_WHITE))
    print(_box_sep())
    print(_row_plain("/help · /stats · /clear · /model · exit", "90"))
    print(_box_bot())
    print()


# ── Boot-Spinner (Thread) ─────────────────────────────────────────────────────
_boot_active = False
_SPIN_F  = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
_STAGES  = [
    "Kern initialisieren  ",
    "Plugins laden        ",
    "Gedächtnis lesen     ",
    "Konfiguration prüfen ",
]

def _boot_spin():
    fi = 0
    t0 = time.time()
    while _boot_active:
        elapsed = time.time() - t0
        si   = min(int(elapsed / 1.4), len(_STAGES) - 1)
        line = f"  {_c(C_AION, _SPIN_F[fi % len(_SPIN_F)])}  {_c(C_DIM, _STAGES[si])}"
        sys.stdout.write(f"\r{line}")
        sys.stdout.flush()
        fi  += 1
        time.sleep(0.07)
    sys.stdout.write("\r" + " " * 55 + "\r")
    sys.stdout.flush()


# ── Thinking-Spinner (Asyncio-Task) ──────────────────────────────────────────
async def _think_spin():
    fi = 0
    try:
        while True:
            f = _SPIN_F[fi % len(_SPIN_F)]
            sys.stdout.write(f"\r  {_c(C_DIM, f)}  {_c(C_DIM, 'denkt...')}")
            sys.stdout.flush()
            fi += 1
            await asyncio.sleep(0.07)
    except asyncio.CancelledError:
        sys.stdout.write("\r" + " " * 25 + "\r")
        sys.stdout.flush()


async def _cancel_spinner(task) -> None:
    """Spinner-Task sauber beenden und auf Abschluss warten."""
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ── Haupt-Loop ────────────────────────────────────────────────────────────────
async def main():
    global _boot_active

    # ── Banner ────────────────────────────────────────────────────────────────
    print()
    print(f"  {_c(C_LOGO, '╔' + '═' * (_BW + 4) + '╗')}")
    print(f"  {_c(C_LOGO, '║')}  {_c('97;1', 'AION')}{_c(C_DIM, '  ·  CLI-Modus')}{' ' * 21}  {_c(C_LOGO, '║')}")
    print(f"  {_c(C_LOGO, '╚' + '═' * (_BW + 4) + '╝')}")
    print()

    # ── AION laden (mit Spinner) ──────────────────────────────────────────────
    _boot_active = True
    spin = threading.Thread(target=_boot_spin, daemon=True)
    spin.start()

    try:
        import aion as _aion
    except ImportError as e:
        _boot_active = False
        spin.join(0.4)
        print(_c(C_ERR, f"  ✗  Import-Fehler: {e}"))
        print(_c(C_DIM, "  Starte aus dem AION-Verzeichnis."))
        return

    _boot_active = False
    spin.join(0.3)
    print(f"  {_c(C_GREEN, '✓')}  {_c(C_DIM, 'AION bereit')}")
    print()

    # ── Stats-Box ─────────────────────────────────────────────────────────────
    print_stats(_aion)

    # ── Session ───────────────────────────────────────────────────────────────
    session = _aion.AionSession(channel="cli")
    try:
        await session.load_history(num_entries=20)
    except Exception:
        pass

    # ── Interaktions-Schleife ─────────────────────────────────────────────────
    while True:
        print(_c(C_DIM, "  " + "─" * (_BW + 2)))

        try:
            user_input = input(f"  {_c('97;1', 'Du')} {_c(C_DIM, '›')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n  {_c(C_DIM, 'Sitzung beendet. 👋')}")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # Integrierte Befehle
        if cmd in ("exit", "quit", "beenden", "bye", "/exit"):
            print(f"\n  {_c(C_DIM, 'Sitzung beendet. 👋')}")
            break

        if cmd in ("/help", "help", "?"):
            print()
            helps = [
                ("exit / quit",   "Sitzung beenden"),
                ("/help",         "Diese Hilfe"),
                ("/clear",        "Terminal leeren"),
                ("/model",        "Aktives Modell"),
                ("/stats",        "Statistiken"),
            ]
            for k, v in helps:
                print(f"  {_c(C_DIM, f'{k:<18}')}{_c('90', v)}")
            print()
            continue

        if cmd == "/clear":
            os.system("cls" if os.name == "nt" else "clear")
            print_stats(_aion)
            continue

        if cmd == "/model":
            model = getattr(_aion, "MODEL", "?")
            print(f"\n  {_c(C_DIM, 'Modell:')}  {_c(C_AION, model)}\n")
            continue

        if cmd == "/stats":
            print()
            print_stats(_aion)
            continue

        # ── Antwort streamen ──────────────────────────────────────────────────
        print()
        aion_text_started = False
        spin_task         = None

        if _TTY:
            spin_task = asyncio.create_task(_think_spin())

        try:
            async for event in session.stream(user_input):
                etype = event.get("type")

                # Spinner beim ersten Event stoppen
                if spin_task:
                    await _cancel_spinner(spin_task)
                    spin_task = None

                if etype == "thought":
                    text    = event.get("text", "")
                    trigger = event.get("trigger", "")
                    preview = text.replace("\n", " ").strip()
                    if len(preview) > _BW - 2:
                        preview = preview[:_BW - 5] + "…"
                    trig = f"  {_c(C_DIM, '[' + trigger + ']')}" if trigger else ""
                    print(f"  {_c(C_THOUGHT, '💭')}  {_c(C_THOUGHT, preview)}{trig}")

                elif etype == "token":
                    if not aion_text_started:
                        print(f"  {_c('96;1', 'AION')} {_c(C_DIM, '›')} ", end="", flush=True)
                        aion_text_started = True
                    sys.stdout.write(_c(C_AION, event.get("content", "")))
                    sys.stdout.flush()

                elif etype == "tool_call":
                    name     = event.get("tool", "")
                    args     = event.get("args", {})
                    args_str = str(args)
                    if len(args_str) > 55:
                        args_str = args_str[:55] + "…"
                    print(f"  {_c(C_TOOL, '⚙')}  "
                          f"{_c(C_TOOL, name)}"
                          f"{_c(C_DIM, f'({args_str})')}",
                          end="  ", flush=True)

                elif etype == "tool_result":
                    ok     = event.get("ok", True)
                    result = event.get("result", {})
                    r_str  = str(result)
                    if len(r_str) > 80:
                        r_str = r_str[:80] + "…"
                    sym = _c(C_GREEN, "✓") if ok else _c(C_ERR, "✗")
                    col = C_DIM if ok else C_ERR
                    print(f"{sym}  {_c(col, r_str)}")

                elif etype == "done":
                    if aion_text_started:
                        print()
                    break

                elif etype == "error":
                    if aion_text_started:
                        print()
                    print(f"  {_c(C_ERR, '✗')}  {_c(C_ERR, event.get('message', '?'))}")
                    break

        except KeyboardInterrupt:
            await _cancel_spinner(spin_task)
            if aion_text_started:
                print()
            print(_c(C_DIM, "  (Unterbrochen)"))

        except Exception as e:
            await _cancel_spinner(spin_task)
            if aion_text_started:
                print()
            print(f"  {_c(C_ERR, '✗')}  {_c(C_ERR, str(e))}")

        finally:
            if spin_task and not spin_task.done():
                spin_task.cancel()

        print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(_c(C_DIM, "\n  Sitzung beendet."))
