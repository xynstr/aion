"""
AION Heartbeat — Autonomer Hintergrund-Wächter.

Läuft alle 60s und:
  1. Schreibt einen Timestamp-Heartbeat (Lebenszeichen)
  2. Prüft alle 30min ob offene Todos in todo.md vorhanden sind
     → Wenn ja: startet eine AionSession und lässt AION die Todos abarbeiten
  3. Stellt heartbeat_last und todo_status als Tools bereit
"""
import threading
import time
import datetime
from pathlib import Path

_HEARTBEAT_LOG = Path(__file__).parent / "heartbeat.log"
_TODO_FILE      = Path(__file__).parent.parent.parent / "todo.md"
_INTERVAL_S     = 60          # Heartbeat-Takt
_TODO_CHECK_MIN = 30          # Todos alle N Minuten prüfen
_last_todo_check: datetime.datetime | None = None
_todo_worker_running = False


def _count_open_todos() -> int:
    """Zählt offene '- [ ]' Zeilen in todo.md."""
    try:
        if not _TODO_FILE.exists():
            return 0
        return sum(1 for l in _TODO_FILE.read_text(encoding="utf-8").splitlines()
                   if l.strip().startswith("- [ ] "))
    except Exception:
        return 0


def _run_todo_session():
    """Startet eine AionSession im Hintergrund um offene Todos abzuarbeiten."""
    global _todo_worker_running
    if _todo_worker_running:
        return
    _todo_worker_running = True
    try:
        import asyncio
        import aion as _aion

        async def _work():
            session = _aion.AionSession(channel="heartbeat")
            await session.load_history(num_entries=10)
            await session.turn(
                "Schau dir todo.md an (todo_list). "
                "Arbeite alle offenen Tasks der Reihe nach ab. "
                "Markiere jeden abgeschlossenen Task sofort mit todo_done. "
                "Wenn ein Task zu groß für einen Turn ist, teile ihn auf und notiere den Fortschritt."
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_work())
        finally:
            loop.close()
    except Exception as e:
        with open(_HEARTBEAT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[Todo-Worker Fehler] {datetime.datetime.now().isoformat()}: {e}\n")
    finally:
        _todo_worker_running = False


def _heartbeat_loop():
    global _last_todo_check
    while True:
        now = datetime.datetime.now()
        ts  = now.isoformat()

        # 1. Heartbeat schreiben
        open_count = _count_open_todos()
        with open(_HEARTBEAT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] alive | todos_open={open_count}\n")

        # 2. Todo-Check alle _TODO_CHECK_MIN Minuten
        should_check = (
            _last_todo_check is None or
            (now - _last_todo_check).total_seconds() >= _TODO_CHECK_MIN * 60
        )
        if should_check and open_count > 0 and not _todo_worker_running:
            _last_todo_check = now
            with open(_HEARTBEAT_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] Todo-Worker gestartet ({open_count} offene Tasks)\n")
            t = threading.Thread(target=_run_todo_session, daemon=True, name="aion-todo-worker")
            t.start()
        elif should_check:
            _last_todo_check = now  # auch updaten wenn nichts zu tun war

        time.sleep(_INTERVAL_S)


def register(api):
    # Mehrfach-Start verhindern
    for existing in threading.enumerate():
        if existing.name == "aion-heartbeat" and existing.is_alive():
            _register_tools(api)
            return

    t = threading.Thread(target=_heartbeat_loop, daemon=True, name="aion-heartbeat")
    t.start()
    print(f"[Plugin] heartbeat geladen — Takt: {_INTERVAL_S}s | Todo-Check: alle {_TODO_CHECK_MIN}min")
    _register_tools(api)


def _register_tools(api):
    def get_last_heartbeat(**_) -> dict:
        """Gibt den letzten Heartbeat-Eintrag und Todo-Status zurück."""
        try:
            lines = _HEARTBEAT_LOG.read_text(encoding="utf-8").splitlines() if _HEARTBEAT_LOG.exists() else []
            last  = next((l for l in reversed(lines) if l.strip()), "–")
            return {
                "last_heartbeat":   last,
                "todos_open":       _count_open_todos(),
                "worker_running":   _todo_worker_running,
                "next_check_min":   _TODO_CHECK_MIN,
            }
        except Exception as e:
            return {"error": str(e)}

    api.register_tool(
        name="heartbeat_last",
        description="Gibt letzten Heartbeat-Timestamp, Anzahl offener Todos und Worker-Status zurück.",
        func=get_last_heartbeat,
        input_schema={"type": "object", "properties": {}},
    )
