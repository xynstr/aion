"""
AION global launcher — installed as 'aion' command via pip install -e .

Usage:
  aion          → Web UI (http://localhost:7000)
  aion --cli    → CLI mode (terminal only)
  aion --help   → show help
"""

import os
import sys
import subprocess
from pathlib import Path

AION_DIR = Path(__file__).parent.resolve()


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print("Usage: aion [--cli]")
        print("  aion        Start Web UI on http://localhost:7000")
        print("  aion --cli  Start CLI mode (no browser)")
        sys.exit(0)

    os.chdir(AION_DIR)

    if "--cli" in args or "-c" in args:
        target = AION_DIR / "aion_cli.py"
        subprocess.run([sys.executable, str(target)])
    else:
        target = AION_DIR / "aion_web.py"
        subprocess.run([sys.executable, str(target)])
