"""
config_store — Zentrales, thread-sicheres Config-Modul für AION.

Ersetzt alle 4 identischen _load_config() / _save_config() Implementierungen
in aion.py, aion_web.py, aion_launcher.py und aion_cli.py.

API:
    load()              → dict
    save(data: dict)    → None
    update(key, value)  → None  (atomares Lesen + Schreiben eines einzelnen Keys)
"""

import json
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


def save(data: dict) -> None:
    """Schreibt config.json thread-sicher."""
    with _lock:
        _CONFIG_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def update(key: str, value) -> None:
    """Atomares Lesen + Schreiben eines einzelnen Keys — race-condition-frei."""
    with _lock:
        cfg = _load_unlocked()
        cfg[key] = value
        _CONFIG_FILE.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
