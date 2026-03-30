"""
aion_config — Konstanten und Konfigurationsfunktionen für AION.
Extrahiert aus aion.py (Zeilen 66–131).
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc

# ── Configuration ─────────────────────────────────────────────────────────────

BOT_DIR      = Path(__file__).parent.resolve()
CONFIG_FILE  = BOT_DIR / "config.json"
MEMORY_FILE   = Path(os.environ.get("AION_MEMORY_FILE", str(BOT_DIR / "aion_memory.json")))
VECTORS_FILE  = BOT_DIR / "aion_memory_vectors.json"
PLUGINS_DIR  = Path(os.environ.get("AION_PLUGINS_DIR", str(BOT_DIR / "plugins")))
TOOLS_DIR    = PLUGINS_DIR
CHARACTER_FILE = BOT_DIR / "character.md"
MAX_MEMORY          = 300
MAX_TOOL_ITERATIONS = 50
MAX_HISTORY_TURNS   = 40
CHUNK_SIZE          = 100000
CHARACTER_MAX_CHARS      = 5_000
RULES_COMPRESS_THRESHOLD = 15_000
LOG_FILE            = BOT_DIR / "aion_events.log"
LOG_MAX_BYTES       = 500 * 1024  # 500 KB


# ── Structured Event Logging ───────────────────────────────────────────────

def _log_event(event_type: str, data: dict) -> None:
    """Schreibt einen strukturierten Log-Eintrag in aion_events.log (JSONL)."""
    try:
        if LOG_FILE.is_file() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            backup = LOG_FILE.with_suffix(".log.1")
            LOG_FILE.rename(backup)
        entry = {"ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "type": event_type}
        entry.update(data)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _load_config() -> dict:
    """Reads config.json. Returns empty dict if not present."""
    if CONFIG_FILE.is_file():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_model_config(model_name: str):
    """Writes the selected model permanently to config.json."""
    cfg = _load_config()
    cfg["model"] = model_name
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
