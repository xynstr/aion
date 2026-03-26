"""
AION global launcher — installed as 'aion' command via pip install -e .

Usage:
  aion          → interactive selector: Web UI or CLI (arrow keys)
  aion --web    → Web UI (http://localhost:7000) directly
  aion --cli    → CLI mode (terminal only) directly
  aion --setup  → re-run onboarding (API keys, model selection)
  aion update   → pull latest version from GitHub & reinstall
  aion --help   → show help
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

AION_DIR  = Path(__file__).parent.resolve()
FLAG_FILE = AION_DIR / "aion_onboarding_complete.flag"


def _ensure_dependencies():
    """Install requirements.txt if core packages are missing."""
    try:
        import fastapi, uvicorn, openai  # noqa: F401
    except ImportError:
        req = AION_DIR / "requirements.txt"
        if req.is_file():
            print("[AION] Installing dependencies…", flush=True)
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req)],
                check=False,
            )
            if result.returncode != 0:
                print("[AION] Warning: some packages failed to install (see above).", flush=True)


def _run_onboarding():
    onboarding = AION_DIR / "onboarding.py"
    if not onboarding.is_file():
        print("[AION] onboarding.py not found — skipping", flush=True)
        return

    # Run in-process so output always appears in the same console window.
    # Using subprocess risks pythonw.exe creating a windowless process that
    # closes immediately before the user can read anything.
    if str(AION_DIR) not in sys.path:
        sys.path.insert(0, str(AION_DIR))
    sys.stdout.flush()
    import importlib.util
    spec = importlib.util.spec_from_file_location("onboarding", str(onboarding))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.run_onboarding()


def _open_browser_delayed(url: str = "http://localhost:7000", delay: float = 2.0):
    def _open():
        import urllib.request
        # Warten bis der Server tatsächlich antwortet (max. 10 Sekunden)
        for _ in range(20):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(url + "/favicon.ico", timeout=1)
                break   # Server antwortet → Browser öffnen
            except Exception:
                continue
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def _run_config_cmd(args: list) -> None:
    """
    aion config list                — show all settings
    aion config get <key>           — read a value
    aion config set <key> <value>   — write a value (JSON-aware)
    aion config unset <key>         — remove an entry
    """
    import json
    import sys
    sys.path.insert(0, str(AION_DIR))
    import config_store as _cs

    sub = args[0] if args else "list"

    if sub == "list":
        cfg = _cs.load()
        if not cfg:
            print("[config] config.json not found or empty.")
            return
        w = max((len(k) for k in cfg), default=0) + 2
        print()
        for k, v in sorted(cfg.items()):
            print(f"  {k:<{w}} {json.dumps(v) if not isinstance(v, str) else v}")
        print()

    elif sub == "get":
        if len(args) < 2:
            print("Usage: aion config get <key>"); return
        key = args[1]
        val = _cs.load().get(key)
        if val is None:
            print(f"[config] '{key}' is not set.")
        else:
            print(f"  {key} = {json.dumps(val) if not isinstance(val, str) else val}")

    elif sub == "set":
        if len(args) < 3:
            print("Usage: aion config set <key> <value>"); return
        key = args[1]
        raw = " ".join(args[2:])
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            val = raw
        _cs.update(key, val)
        print(f"[config] {key} = {val!r}")

    elif sub == "unset":
        if len(args) < 2:
            print("Usage: aion config unset <key>"); return
        key = args[1]
        cfg = _cs.load()
        if key in cfg:
            del cfg[key]
            _cs.save(cfg)
            print(f"[config] '{key}' removed.")
        else:
            print(f"[config] '{key}' not found in config.json.")

    else:
        print("Usage: aion config [list | get <key> | set <key> <value> | unset <key>]")


def _enable_win_vt():
    """Aktiviert ANSI/VT100-Verarbeitung im Windows-Terminal (PowerShell, cmd)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ENABLE_VT = 0x0004
            k32 = ctypes.windll.kernel32
            h   = k32.GetStdHandle(-11)        # STD_OUTPUT_HANDLE
            m   = ctypes.c_ulong()
            k32.GetConsoleMode(h, ctypes.byref(m))
            k32.SetConsoleMode(h, m.value | ENABLE_VT)
        except Exception:
            pass


def _choose_mode() -> str:
    """Arrow-key selector: returns 'web' or 'cli'."""
    _enable_win_vt()
    items   = ["Web UI  (http://localhost:7000)", "CLI     (terminal only)"]
    n       = len(items)
    idx     = 0
    _TTY    = sys.stdout.isatty()

    def _esc(code: str) -> str:
        return f"\x1b[{code}m" if _TTY else ""

    def _render(sel: int) -> None:
        for i, item in enumerate(items):
            if i == sel:
                print(f"  {_esc('92;1')}>{_esc('0')} {_esc('97;1')}{item}{_esc('0')}")
            else:
                print(f"    {_esc('2')}{item}{_esc('0')}")
        sys.stdout.flush()

    def _erase(count: int) -> None:
        sys.stdout.write(f"\x1b[{count}A\x1b[J")
        sys.stdout.flush()

    print(f"\n  {_esc('2')}Arrow keys ↑↓  ·  Enter to select{_esc('0')}")

    if not _TTY:
        _render(idx)
        while True:
            val = input("  Choice (1=Web / 2=CLI): ").strip()
            if val == "1": return "web"
            if val == "2": return "cli"

    _render(idx)
    try:
        if sys.platform == "win32":
            import msvcrt
            while True:
                key = msvcrt.getch()
                if key in (b'\r', b'\n'):
                    break
                if key in (b'\x00', b'\xe0'):
                    k2 = msvcrt.getch()
                    if k2 == b'H':
                        idx = (idx - 1) % n
                    elif k2 == b'P':
                        idx = (idx + 1) % n
                elif key == b'\x1b':
                    raise KeyboardInterrupt
                _erase(n)
                _render(idx)
        else:
            try:
                import tty, termios
            except ImportError:
                # Minimal POSIX system without tty/termios — fall back to plain input
                _erase(n)
                while True:
                    val = input("  Choice (1=Web / 2=CLI): ").strip()
                    if val == "1": idx = 0; break
                    if val == "2": idx = 1; break
            else:
                fd   = sys.stdin.fileno()
                old  = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    while True:
                        ch = sys.stdin.read(1)
                        if ch in ('\r', '\n'):
                            break
                        if ch == '\x1b':
                            nxt = sys.stdin.read(2)
                            if nxt == '[A':
                                idx = (idx - 1) % n
                            elif nxt == '[B':
                                idx = (idx + 1) % n
                        _erase(n)
                        _render(idx)
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except KeyboardInterrupt:
        print("\n[AION] Aborted.", flush=True)
        sys.exit(0)

    _erase(n)
    _render(idx)
    print()
    return "cli" if idx == 1 else "web"


def _run_update():
    """Führt git pull + pip install -e . aus um AION zu aktualisieren."""
    _enable_win_vt()
    git_dir = AION_DIR / ".git"
    if not git_dir.is_dir():
        print("[AION] Kein .git-Verzeichnis gefunden — Update nicht möglich.")
        print("       Klone das Repository mit 'git clone' um Updates zu erhalten.")
        return

    print("[AION] Update wird gestartet…\n", flush=True)

    # 1. git pull
    print("  → git pull", flush=True)
    result = subprocess.run(["git", "pull"], cwd=str(AION_DIR), check=False)
    if result.returncode != 0:
        print("\n[AION] git pull fehlgeschlagen. Bitte manuell prüfen.", flush=True)
        return

    # 2. pip install -e .
    print("\n  → pip install -e .", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", "."],
        cwd=str(AION_DIR), check=False,
    )
    if result.returncode != 0:
        print("\n[AION] pip install fehlgeschlagen. Bitte manuell prüfen.", flush=True)
        return

    # Neue Version anzeigen
    try:
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]  # Python 3.10 fallback
        text = (AION_DIR / "pyproject.toml").read_text(encoding="utf-8")
        data = tomllib.loads(text)
        new_ver = data.get("project", {}).get("version", "?")
    except Exception:
        try:
            import re
            text = (AION_DIR / "pyproject.toml").read_text(encoding="utf-8")
            m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
            new_ver = m.group(1) if m else "?"
        except Exception:
            new_ver = "?"

    print(f"\n[AION] Update erfolgreich! Version {new_ver} ist jetzt aktiv.", flush=True)
    print("       Starte 'aion' um die neue Version zu nutzen.\n", flush=True)


def _check_update_banner():
    """Zeigt einen Hinweis an wenn eine neuere Version verfügbar ist (nicht-blockierend)."""
    try:
        import sys as _sys
        if str(AION_DIR) not in _sys.path:
            _sys.path.insert(0, str(AION_DIR))
        from plugins.updater.updater import _update_state
        if _update_state.get("update_available"):
            latest  = _update_state.get("latest_version", "?")
            current = _update_state.get("current_version", "?")
            _enable_win_vt()
            print(
                f"\n  \x1b[93;1m⚡ Update verfügbar: {current} → {latest}"
                f" — 'aion update' ausführen\x1b[0m",
                flush=True,
            )
    except Exception:
        pass


def _pause_on_error():
    """On Windows, pause so the user can read the error before the window closes."""
    if sys.platform == "win32":
        try:
            input("\nPress Enter to close...")
        except Exception:
            pass


def main():
    try:
        _main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        msg = traceback.format_exc()
        # Write to log file so it's always readable
        try:
            log = AION_DIR / "aion_error.log"
            log.write_text(msg, encoding="utf-8")
            print(f"\n[AION] Fatal error — details saved to: {log}", flush=True)
        except Exception:
            pass
        print(f"\n[AION] Fatal error: {e}", flush=True)
        print(msg, flush=True)
        _pause_on_error()
        sys.exit(1)


def _main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print("Usage: aion [--web | --cli] [--setup] [config <subcommand>] [update]")
        print("  aion                      Interactive mode selector (↑↓ arrow keys)")
        print("  aion --web                Web UI  →  http://localhost:7000")
        print("  aion --cli                CLI mode (no browser)")
        print("  aion --setup              Re-run setup (API keys, model selection)")
        print("  aion update               Pull latest version & reinstall")
        print("  aion config list          Show all settings")
        print("  aion config get <key>     Read a setting")
        print("  aion config set <key> <v> Write a setting")
        print("  aion config unset <key>   Remove a setting")
        print()
        print("Common keys:")
        print("  model             Active LLM model")
        print("  check_model       Model for internal YES/NO checks (cost optimization)")
        print("  max_history_turns Conversation history limit (default: 40)")
        print("  tts_engine        TTS engine: edge / sapi5 / pyttsx3 / off")
        print("  tts_voice         TTS voice name")
        print("  thinking_level    Reasoning depth: off / minimal / standard / deep / extreme")
        print("  browser_headless  Browser mode: true/false")
        sys.exit(0)

    if args and args[0] == "update":
        _run_update()
        return

    if args and args[0] == "config":
        _run_config_cmd(args[1:])
        return

    os.chdir(AION_DIR)

    if "--setup" in args:
        _ensure_dependencies()
        FLAG_FILE.unlink(missing_ok=True)
        _run_onboarding()
        print("\n[AION] Setup complete. Run 'aion' to start.", flush=True)
        return

    # First run: install + onboarding
    _ensure_dependencies()
    if not FLAG_FILE.exists():
        print("\n[AION] First run — starting setup…\n")
        _run_onboarding()

    # Launch — force python.exe (not pythonw.exe) so the console stays open
    python = sys.executable
    if sys.platform == "win32":
        from pathlib import Path as _Path
        _p = _Path(python)
        if _p.stem.lower() == "pythonw":
            python = str(_p.with_name("python.exe"))

    _check_update_banner()

    if "--cli" in args or "-c" in args:
        mode = "cli"
    elif "--web" in args or "-w" in args:
        mode = "web"
    else:
        mode = _choose_mode()

    if mode == "cli":
        try:
            subprocess.run([python, str(AION_DIR / "aion_cli.py")])
        except KeyboardInterrupt:
            print("\n[AION] Beendet.", flush=True)
    else:
        print(f"[AION] Starting Web UI → http://localhost:7000", flush=True)
        _open_browser_delayed()
        proc = subprocess.Popen([python, str(AION_DIR / "aion_web.py")])
        try:
            proc.wait()
        except KeyboardInterrupt:
            if sys.platform == "win32":
                import signal as _sig
                try:
                    proc.send_signal(_sig.CTRL_C_EVENT)
                except Exception:
                    proc.terminate()
            else:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("\n[AION] Beendet.", flush=True)


if __name__ == "__main__":
    main()
