"""
AION Plugin: Scheduler — Geplante Aufgaben wie ein Cron-Job
==============================================================
Ermöglicht es, AION-Aufgaben zu festen Uhrzeiten automatisch auszuführen.

Beispiel:
  schedule_add(name="Morgen-Brief", time="08:00", days="täglich",
               task="Lese meine Emails, extrahiere Termine und schreibe mir eine Zusammenfassung via Telegram.")

AION führt die Aufgabe dann täglich um 08:00 selbstständig aus und sendet das Ergebnis
per Telegram (wenn konfiguriert).
"""

import asyncio
import json
import os
import threading
import uuid
from datetime import datetime, time as dtime
from pathlib import Path

_TASKS_FILE = Path(__file__).parent / "tasks.json"
_running     = False
_thread      = None


# ── Persistenz ────────────────────────────────────────────────────────────────

def _load_tasks() -> list[dict]:
    if _TASKS_FILE.is_file():
        try:
            return json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_tasks(tasks: list[dict]) -> None:
    _TASKS_FILE.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Zeitprüfung ───────────────────────────────────────────────────────────────

_DAYS_MAP = {
    "mo": 0, "mon": 0, "montag": 0, "monday": 0,
    "di": 1, "tue": 1, "dienstag": 1, "tuesday": 1,
    "mi": 2, "wed": 2, "mittwoch": 2, "wednesday": 2,
    "do": 3, "thu": 3, "donnerstag": 3, "thursday": 3,
    "fr": 4, "fri": 4, "freitag": 4, "friday": 4,
    "sa": 5, "sat": 5, "samstag": 5, "saturday": 5,
    "so": 6, "sun": 6, "sonntag": 6, "sunday": 6,
    "täglich": -1, "daily": -1, "jeden tag": -1, "every day": -1,
    "werktags": list(range(5)), "weekdays": list(range(5)),
    "wochenende": [5, 6], "weekend": [5, 6],
}

def _parse_days(days_str: str) -> list[int] | int:
    """Gibt -1 für täglich zurück, sonst Liste von Wochentag-Indizes (0=Mo)."""
    s = days_str.strip().lower()
    if s in _DAYS_MAP:
        v = _DAYS_MAP[s]
        return v if isinstance(v, list) else ([-1] if v == -1 else [v])
    # Komma-getrennte Liste: "mo,mi,fr"
    parts = [p.strip() for p in s.split(",")]
    result = []
    for p in parts:
        v = _DAYS_MAP.get(p)
        if v == -1:
            return [-1]
        if isinstance(v, list):
            result.extend(v)
        elif v is not None:
            result.append(v)
    return result or [-1]


def _is_due(task: dict, now: datetime) -> bool:
    """Prüft ob ein Task jetzt fällig ist (Minute-genau, einmal pro Minute)."""
    if not task.get("enabled", True):
        return False

    # Uhrzeit parsen
    try:
        h, m = map(int, task["time"].split(":"))
        task_time = dtime(h, m)
    except Exception:
        return False

    if now.hour != task_time.hour or now.minute != task_time.minute:
        return False

    # Wochentag prüfen
    days = _parse_days(task.get("days", "täglich"))
    if days != [-1] and now.weekday() not in days:
        return False

    # Heute schon gelaufen?
    last_run = task.get("last_run", "")
    if last_run and last_run.startswith(now.strftime("%Y-%m-%d")):
        return False

    return True


# ── Task ausführen ─────────────────────────────────────────────────────────────

async def _execute_task(task: dict) -> None:
    """Führt einen Task aus — erstellt eine eigene AionSession und ruft turn() auf."""
    import aion as _aion

    task_id   = task.get("id", "?")
    task_name = task.get("name", "Unbenannt")
    task_text = task.get("task", "")

    print(f"[Scheduler] Task '{task_name}' (ID: {task_id}) startet um {datetime.now().strftime('%H:%M')}")

    # last_run sofort setzen damit kein Doppel-Start passiert
    tasks = _load_tasks()
    for t in tasks:
        if t.get("id") == task_id:
            t["last_run"] = datetime.now().isoformat()
            break
    _save_tasks(tasks)

    try:
        session = _aion.AionSession(channel="scheduler")
        result  = await session.turn(task_text)

        print(f"[Scheduler] Task '{task_name}' abgeschlossen.")

        # Ergebnis via Telegram senden (wenn Plugin verfügbar)
        if "send_telegram_message" in _aion._plugin_tools:
            header  = f"⏰ *Geplante Aufgabe: {task_name}*\n\n"
            await _aion._dispatch("send_telegram_message", {"message": header + result})

        # Ergebnis im Gedächtnis festhalten
        _aion.memory.record(
            category="conversation",
            summary=f"Geplante Aufgabe: {task_name}",
            lesson=f"Scheduler führte '{task_name}' aus. Ergebnis: {result[:200]}",
            success=True,
        )

    except Exception as e:
        print(f"[Scheduler] Fehler bei Task '{task_name}': {e}")
        if "send_telegram_message" in _aion._plugin_tools:
            try:
                await _aion._dispatch("send_telegram_message", {
                    "message": f"❌ Geplante Aufgabe *{task_name}* fehlgeschlagen:\n{e}"
                })
            except Exception:
                pass


# ── Hintergrund-Loop ──────────────────────────────────────────────────────────

def _scheduler_loop() -> None:
    """Läuft in einem eigenen Thread, prüft jede Minute ob Tasks fällig sind."""
    import time

    last_checked_minute = -1

    while _running:
        now = datetime.now()

        # Nur einmal pro Minute prüfen
        if now.minute != last_checked_minute:
            last_checked_minute = now.minute
            tasks = _load_tasks()
            for task in tasks:
                if _is_due(task, now):
                    # asyncio in eigenem Thread → neuen Event-Loop nutzen
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(_execute_task(task))
                    finally:
                        loop.close()

        time.sleep(10)  # alle 10 Sekunden prüfen (genug für Minutengenauigkeit)


# ── Tool-Funktionen ───────────────────────────────────────────────────────────

def _schedule_add(input: dict) -> dict:
    name  = input.get("name", "").strip()
    time_ = input.get("time", "").strip()
    days  = input.get("days", "täglich").strip()
    task  = input.get("task", "").strip()

    if not name or not time_ or not task:
        return {"error": "name, time und task sind Pflichtfelder."}

    # Format prüfen
    try:
        h, m = map(int, time_.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except Exception:
        return {"error": f"Ungültige Uhrzeit '{time_}'. Format: HH:MM (z.B. '08:00')"}

    tasks = _load_tasks()
    entry = {
        "id":       str(uuid.uuid4())[:8],
        "name":     name,
        "time":     f"{h:02d}:{m:02d}",
        "days":     days,
        "task":     task,
        "enabled":  True,
        "created":  datetime.now().isoformat(),
        "last_run": None,
    }
    tasks.append(entry)
    _save_tasks(tasks)
    return {"ok": True, "id": entry["id"], "message": f"Task '{name}' angelegt — läuft täglich um {entry['time']}."}


def _schedule_list(input: dict) -> dict:
    tasks = _load_tasks()
    if not tasks:
        return {"tasks": [], "message": "Keine geplanten Aufgaben."}
    summary = []
    for t in tasks:
        summary.append({
            "id":       t.get("id"),
            "name":     t.get("name"),
            "time":     t.get("time"),
            "days":     t.get("days"),
            "enabled":  t.get("enabled", True),
            "last_run": t.get("last_run"),
            "task":     t.get("task", "")[:80] + ("…" if len(t.get("task", "")) > 80 else ""),
        })
    return {"tasks": summary, "count": len(tasks)}


def _schedule_remove(input: dict) -> dict:
    task_id = input.get("id", "").strip()
    name    = input.get("name", "").strip()
    if not task_id and not name:
        return {"error": "id oder name angeben."}

    tasks   = _load_tasks()
    before  = len(tasks)
    tasks   = [t for t in tasks if t.get("id") != task_id and t.get("name") != name]
    removed = before - len(tasks)
    _save_tasks(tasks)
    return {"ok": True, "removed": removed}


def _schedule_toggle(input: dict) -> dict:
    task_id = input.get("id", "").strip()
    enabled = input.get("enabled", None)
    tasks   = _load_tasks()
    for t in tasks:
        if t.get("id") == task_id:
            t["enabled"] = not t.get("enabled", True) if enabled is None else bool(enabled)
            _save_tasks(tasks)
            state = "aktiviert" if t["enabled"] else "deaktiviert"
            return {"ok": True, "id": task_id, "enabled": t["enabled"], "message": f"Task {state}."}
    return {"error": f"Task mit ID '{task_id}' nicht gefunden."}


# ── Plugin registrieren ───────────────────────────────────────────────────────

def register(api):
    global _running, _thread

    # Hintergrund-Thread starten
    _running = True
    _thread  = threading.Thread(target=_scheduler_loop, daemon=True, name="aion-scheduler")
    _thread.start()
    print("[Plugin] scheduler geladen — Cron-Loop aktiv (Prüfintervall: 10s)")

    api.register_tool(
        name="schedule_add",
        description=(
            "Plant eine AION-Aufgabe zu einer festen Uhrzeit. "
            "AION führt die Aufgabe dann automatisch aus und sendet das Ergebnis per Telegram. "
            "Beispiel: täglich um 06:00 Emails lesen und Termine in Kalender eintragen, "
            "um 08:00 Zusammenfassung senden."
        ),
        func=_schedule_add,
        input_schema={
            "type": "object",
            "properties": {
                "name":  {"type": "string", "description": "Kurzer Name für die Aufgabe, z.B. 'Morgen-Brief'"},
                "time":  {"type": "string", "description": "Uhrzeit im Format HH:MM, z.B. '08:00' oder '06:30'"},
                "days":  {"type": "string", "description": "Wann ausführen: 'täglich', 'werktags', 'wochenende', oder Tage wie 'mo,mi,fr'. Standard: täglich"},
                "task":  {"type": "string", "description": "Vollständige Aufgabenbeschreibung die AION ausführen soll — so detailliert wie eine normale Nutzer-Nachricht"},
            },
            "required": ["name", "time", "task"],
        },
    )

    api.register_tool(
        name="schedule_list",
        description="Listet alle geplanten Aufgaben auf (Name, Uhrzeit, Tage, letzte Ausführung).",
        func=_schedule_list,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="schedule_remove",
        description="Löscht eine geplante Aufgabe anhand ihrer ID oder ihres Namens.",
        func=_schedule_remove,
        input_schema={
            "type": "object",
            "properties": {
                "id":   {"type": "string", "description": "Task-ID (aus schedule_list)"},
                "name": {"type": "string", "description": "Task-Name als Alternative zur ID"},
            },
        },
    )

    api.register_tool(
        name="schedule_toggle",
        description="Aktiviert oder deaktiviert eine geplante Aufgabe (ohne sie zu löschen).",
        func=_schedule_toggle,
        input_schema={
            "type": "object",
            "properties": {
                "id":      {"type": "string", "description": "Task-ID"},
                "enabled": {"type": "boolean", "description": "true = aktivieren, false = deaktivieren. Ohne Angabe: umschalten."},
            },
            "required": ["id"],
        },
    )
