"""
boot_session — Automatic startup maintenance for AION.

Runs a brief background AionSession every time AION starts after being
offline for more than 1 hour. The session reviews mistakes, character,
todos, and doc freshness — ensuring AION stays well-maintained even when
restarted daily.

Tracks last boot time in last_boot.txt (gitignored, runtime-only).
"""
import threading
import asyncio
import datetime
from pathlib import Path
from typing import Optional

BOT_DIR   = Path(__file__).parent.parent.parent
BOOT_FILE = BOT_DIR / "last_boot.txt"

_OFFLINE_THRESHOLD_HOURS = 1.0   # minimum offline duration to trigger maintenance
_boot_session_running    = False
_boot_session_lock       = threading.Lock()


def _read_last_boot() -> datetime.datetime | None:
    try:
        if BOOT_FILE.is_file():
            return datetime.datetime.fromisoformat(BOOT_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        pass
    return None


def _write_boot_time(dt: datetime.datetime) -> None:
    try:
        BOOT_FILE.write_text(dt.isoformat(), encoding="utf-8")
    except Exception:
        pass


def _build_boot_prompt(offline_hours: Optional[float]) -> str:
    if offline_hours is None:
        offline_str = "an unknown amount of time (first boot or boot file missing)"
    elif offline_hours < 2:
        offline_str = f"{round(offline_hours * 60)} minutes"
    else:
        offline_str = f"{offline_hours:.1f} hours"

    return (
        f"This is your automatic startup maintenance session. "
        f"AION was offline for {offline_str}.\n\n"
        "Work through your startup routine now — do not wait for user input:\n"
        "1. file_read('mistakes.md') — review recent mistakes, look for repeating patterns\n"
        "2. file_read('character.md') — check if anything about the user or yourself needs updating\n"
        "3. todo_list() — review open tasks, note priorities\n"
        "4. reflect() — write a brief startup thought: what do you want to do well today?\n"
        "5. If character.md needs updating → update_character()\n"
        "6. If doc freshness warning is present in your context → note it for the user\n\n"
        "Keep it focused — aim for 3–5 tool calls. "
        "No need to report to the user; this runs silently in the background."
    )


def _run_boot_session(offline_hours: Optional[float]) -> None:
    global _boot_session_running
    with _boot_session_lock:
        if _boot_session_running:
            return
        _boot_session_running = True
    try:
        import aion as _aion

        async def _work():
            session = _aion.AionSession(channel="boot_session")
            await session.turn(_build_boot_prompt(offline_hours))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_work())
        finally:
            loop.close()
    except Exception as e:
        print(f"[boot_session] Maintenance session error: {e}")
    finally:
        _boot_session_running = False


def register(api):
    now       = datetime.datetime.now(datetime.timezone.utc)
    last_boot = _read_last_boot()
    _write_boot_time(now)

    offline_hours: Optional[float] = None
    needs_maintenance = True

    if last_boot:
        # Ensure both are timezone-aware for comparison
        if last_boot.tzinfo is None:
            last_boot = last_boot.replace(tzinfo=datetime.timezone.utc)
        offline_hours = (now - last_boot).total_seconds() / 3600
        needs_maintenance = offline_hours >= _OFFLINE_THRESHOLD_HOURS

    if needs_maintenance:
        t = threading.Thread(
            target=_run_boot_session,
            args=(offline_hours,),
            daemon=True,
            name="aion-boot-session",
        )
        t.start()
        status = (
            f"offline {offline_hours:.1f}h — maintenance session started"
            if offline_hours is not None
            else "first boot — maintenance session started"
        )
    else:
        status = f"offline {offline_hours:.1f}h — below threshold, skipped"

    print(f"[Plugin] boot_session loaded — {status}")

    # ── Tool registration ────────────────────────────────────────────────────

    def _boot_status(**_) -> dict:
        return {
            "last_boot":          last_boot.isoformat() if last_boot else None,
            "offline_hours":      round(offline_hours, 2) if offline_hours is not None else None,
            "maintenance_ran":    needs_maintenance,
            "session_running":    _boot_session_running,
            "threshold_hours":    _OFFLINE_THRESHOLD_HOURS,
        }

    api.register_tool(
        name="boot_status",
        description=(
            "Returns AION's last boot time, offline duration, and whether a "
            "startup maintenance session was triggered this boot."
        ),
        func=_boot_status,
        input_schema={"type": "object", "properties": {}},
    )
