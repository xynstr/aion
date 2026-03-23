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


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print("Usage: aion [--cli] [--setup]")
        print("  aion         Web UI  →  http://localhost:7000")
        print("  aion --cli   CLI mode (no browser)")
        print("  aion --setup Re-run setup (API keys, model selection)")
        sys.exit(0)

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
