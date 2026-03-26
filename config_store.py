"""
config_store — Zentrales, thread-sicheres Config-Modul für AION.

Ersetzt alle 4 identischen _load_config() / _save_config() Implementierungen
in aion.py, aion_web.py, aion_launcher.py und aion_cli.py.

API:
    load()                  → dict
    save(data: dict)        → None
    update(key, value)      → None  (atomares Lesen + Schreiben eines einzelnen Keys)
    find_claude_bin()       → str | None
"""

import glob as _glob
import json
import os
import shutil
import sys
import threading
from pathlib import Path

_CONFIG_FILE = Path(__file__).parent / "config.json"
_lock = threading.Lock()


def load() -> dict:
    """Lädt config.json thread-sicher. Gibt {} bei Fehler zurück."""
    with _lock:
        return _load_unlocked()


def _load_unlocked() -> dict:
    """Internes Laden ohne Lock — nur aufrufen wenn Lock bereits gehalten wird."""
    if _CONFIG_FILE.is_file():
        try:
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_unlocked(data: dict) -> None:
    """Schreibt atomisch via Temp-Datei — verhindert korrupte config.json bei Schreibfehlern."""
    tmp = _CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(_CONFIG_FILE)


def save(data: dict) -> None:
    """Schreibt config.json thread-sicher und atomar."""
    with _lock:
        _write_unlocked(data)


def update(key: str, value) -> None:
    """Atomares Lesen + Schreiben eines einzelnen Keys — race-condition-frei."""
    with _lock:
        cfg = _load_unlocked()
        cfg[key] = value
        _write_unlocked(cfg)


def find_claude_bin() -> "str | None":
    """Sucht die claude CLI in PATH und bekannten Installationspfaden (Windows/macOS/Linux)."""
    found = shutil.which("claude")
    if found:
        return found
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        appdata   = os.environ.get("APPDATA") or ""
        localdata = os.environ.get("LOCALAPPDATA") or ""
        candidates = [
            *(  [os.path.join(appdata, "npm", "claude.cmd"),
                 os.path.join(appdata, "npm", "claude")]
                if appdata else []  ),
            os.path.join(home, ".claude", "local", "claude.exe"),
            os.path.join(home, ".claude", "local", "claude"),
            *(  _glob.glob(os.path.join(localdata, "Microsoft", "WinGet",
                    "Packages", "Anthropic.Claude*", "**", "claude.exe"),
                    recursive=True)
                if localdata else []  ),
        ]
    else:
        candidates = [
            os.path.join(home, ".npm-global", "bin", "claude"),
            os.path.join(home, ".local", "bin", "claude"),
            os.path.join(home, ".claude", "local", "claude"),
            "/usr/local/bin/claude",
            "/usr/bin/claude",
        ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None
