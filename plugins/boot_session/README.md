Automatic startup maintenance — runs a background session when AION restarts after ≥1h offline.

## What it does
On every AION startup, `boot_session` checks how long AION was offline (via `last_boot.txt`).
If offline ≥ 1 hour, it spawns a silent background AionSession that:
- Reviews `mistakes.md` for recurring patterns
- Checks `character.md` for gaps
- Lists open todos
- Writes a startup reflection
- Updates `character.md` if needed

Designed for users who stop and restart AION daily — ensures maintenance happens
even without long-running scheduled tasks.

## Files
| File | Purpose |
|------|---------|
| `last_boot.txt` | Timestamp of last boot (gitignored, runtime only) |

## Tools
| Tool | Description |
|------|-------------|
| `boot_status` | Returns last boot time, offline duration, maintenance status |

## Configuration
Edit `_OFFLINE_THRESHOLD_HOURS` in `boot_session.py` (default: 1.0h) to change
the minimum offline duration required to trigger maintenance.
