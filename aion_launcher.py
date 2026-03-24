"""
AION global launcher — installed as 'aion' command via pip install -e .

Usage:
  aion          → Web UI (http://localhost:7000) + opens browser
  aion --cli    → CLI mode (terminal only)
  aion --setup  → re-run onboarding (API keys, model selection)
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
            print("[AION] Installing dependencies…")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req), "-q"],
                check=False,
            )


def _run_onboarding():
    onboarding = AION_DIR / "onboarding.py"
    if not onboarding.is_file():
        print("[AION] onboarding.py not found — skipping", flush=True)
        return
    sys.stdout.flush()
    result = subprocess.run(
        [sys.executable, "-u", str(onboarding)],
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    if result.returncode != 0:
        print("\n[AION] Setup cancelled.", flush=True)
        sys.exit(1)


def _open_browser_delayed(url: str = "http://localhost:7000", delay: float = 2.0):
    def _open():
        time.sleep(delay)
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
    config_path = AION_DIR / "config.json"

    def _load() -> dict:
        if config_path.is_file():
            try:
                return json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(cfg: dict) -> None:
        config_path.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    sub = args[0] if args else "list"

    if sub == "list":
        cfg = _load()
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
        val = _load().get(key)
        if val is None:
            print(f"[config] '{key}' is not set.")
        else:
            import json as _j
            print(f"  {key} = {_j.dumps(val) if not isinstance(val, str) else val}")

    elif sub == "set":
        if len(args) < 3:
            print("Usage: aion config set <key> <value>"); return
        key = args[1]
        raw = " ".join(args[2:])
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            val = raw
        cfg = _load()
        cfg[key] = val
        _save(cfg)
        print(f"[config] {key} = {val!r}")

    elif sub == "unset":
        if len(args) < 2:
            print("Usage: aion config unset <key>"); return
        key = args[1]
        cfg = _load()
        if key in cfg:
            del cfg[key]
            _save(cfg)
            print(f"[config] '{key}' removed.")
        else:
            print(f"[config] '{key}' not found in config.json.")

    else:
        print("Usage: aion config [list | get <key> | set <key> <value> | unset <key>]")


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print("Usage: aion [--cli] [--setup] [config <subcommand>]")
        print("  aion                      Web UI  →  http://localhost:7000")
        print("  aion --cli                CLI mode (no browser)")
        print("  aion --setup              Re-run setup (API keys, model selection)")
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

    # Launch
    if "--cli" in args or "-c" in args:
        subprocess.run([sys.executable, str(AION_DIR / "aion_cli.py")])
    else:
        print(f"[AION] Starting Web UI → http://localhost:7000")
        _open_browser_delayed()
        subprocess.run([sys.executable, str(AION_DIR / "aion_web.py")])
