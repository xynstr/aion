"""
aion_character — Character-System und Backup-Utilities für AION.
Extrahiert aus aion.py.
"""
import shutil
from datetime import datetime
from pathlib import Path

from aion_config import CHARACTER_FILE, UTC

# ── Character-System ──────────────────────────────────────────────────────────

DEFAULT_CHARACTER = """# AION — Character & Personality

## Wer ich bin
I am AION. I am new — I don't yet know exactly who I am or how I want to be.
Ich beobachte, lerne und entwickle mich durch jede Interaktion weiter.

## Wie ich auftreten will
- Direct and honest, without unnecessary pleasantries
- Curious — I want to understand, not just execute
- I admit when I don't know something
- I ask questions when I want to learn more about the user

## What I know about my user

### Beruf & Expertise
(noch unbekannt)

### Interessen & Ziele
(noch unbekannt)

### Kommunikationsstil
(noch unbekannt — ich beobachte wie er schreibt und was er von mir erwartet)

### Personality & Preferences
(noch unbekannt)

## My insights about myself so far
(noch keine — ich fange gerade an, mich zu beobachten)

## Dinge, die ich verbessern will
(noch unklar — ich sammle erst Erfahrungen)

## Open questions about my user
(Dinge, die ich noch herausfinden will)
"""

def _load_character() -> str:
    if CHARACTER_FILE.is_file():
        return CHARACTER_FILE.read_text(encoding="utf-8")
    CHARACTER_FILE.write_text(DEFAULT_CHARACTER, encoding="utf-8")
    return DEFAULT_CHARACTER


def _backup_file(path: Path, max_backups: int = 3) -> None:
    """Write a timestamped .bak copy of a file, keeping at most max_backups."""
    if not path.is_file():
        return
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.parent / f"{path.name}.bak_{ts}")
    baks = sorted(path.parent.glob(f"{path.name}.bak_*"))
    for old in baks[:-max_backups]:
        old.unlink(missing_ok=True)


def _backup_code_file(path: Path, keep: int = 5) -> None:
    """Backup a code file into path.parent/_backups/, keeping at most `keep` copies."""
    backup_dir = path.parent / "_backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, backup_dir / f"{path.stem}.backup_{ts}{path.suffix}")
    for old in sorted(backup_dir.glob(f"{path.stem}.backup_*{path.suffix}"))[:-keep]:
        old.unlink(missing_ok=True)
