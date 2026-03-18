"""
AION Plugin: Scheduler — Geplante Aufgaben (Uhrzeiten + Intervalle)
=====================================================================
Zwei Modi:
  1. Feste Uhrzeit:  schedule_add(name="Brief", time="08:00", days="werktags", task="...")
  2. Intervall:      schedule_add(name="Ping",  interval="5m", task="...")

Beispiele für interval:
  "30s"   = alle 30 Sekunden
  "5m"    = alle 5 Minuten
  "1h"    = jede Stunde
  "2h30m" = alle 2 Stunden 30 Minuten
"""

import asyncio
import json
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


# ── Intervall-Parser ──────────────────────────────────────────────────────────

def _parse_interval(s: str) -> int | None:
    """Parst eine Intervall-Angabe und gibt Sekunden zurück.

    Unterstützt: "30s", "5m", "2h", "1h30m", "5 Minuten", "alle 10 Minuten", etc.
    Gibt None zurück wenn nicht parsbar.
    """
    import re
    if not s:
        return None
    s = s.lower().strip()
    # Präfixe entfernen: "alle", "every", "jede", "jeden"
    s = re.sub(r'^(alle|every|jede[rns]?|jeden)\s+', '', s)
    # Deutsche Wörter ersetzen
    s = s.replace("stunden", "h").replace("stunde", "h")
    s = s.replace("minuten", "m").replace("minute", "m")
    s = s.replace("sekunden", "s").replace("sekunde", "s")
    s = s.replace(" ", "")

    total = 0
    # Pattern: optionale Zahl + Einheit (mehrfach, z.B. "1h30m")
    for num, unit in re.findall(r'(\d+(?:\.\d+)?)([hms])', s):
        val = float(num)
        if unit == "h":
            total += int(val * 3600)
        elif unit == "m":
            total += int(val * 60)
        elif unit == "s":
            total += int(val)
    # Nur Zahl ohne Einheit → Minuten
    if total == 0:
        m = re.match(r'^(\d+)$', s)
        if m:
            total = int(m.group(1)) * 60

    return total if total > 0 else None


def _interval_to_str(seconds: int) -> str:
    """Lesbare Darstellung: 3600 → '1h', 90 → '1m 30s', 300 → '5m'"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s:
        parts.append(f"{s}s")
    return " ".join(parts) or "0s"


# ── Uhrzeit-Parsing ──────────────────────────────────────────────────────────

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

def _parse_days(days_str: str) -> list[int]:
    s = days_str.strip().lower()
    if s in _DAYS_MAP:
        v = _DAYS_MAP[s]
        return v if isinstance(v, list) else ([-1] if v == -1 else [v])
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


# ── Fälligkeitsprüfung ────────────────────────────────────────────────────────

def _is_due(task: dict, now: datetime) -> bool:
    """Prüft ob ein Task jetzt fällig ist."""
    if not task.get("enabled", True):
        return False

    # ── Intervall-Modus ───────────────────────────────────────────────────────
    interval_sec = task.get("interval_seconds")
    if interval_sec:
        last_run = task.get("last_run")
        if not last_run:
            return True  # Noch nie gelaufen → sofort starten
        try:
            last_dt = datetime.fromisoformat(last_run)
            elapsed = (now - last_dt).total_seconds()
            return elapsed >= interval_sec
        except Exception:
            return True

    # ── Uhrzeit-Modus ─────────────────────────────────────────────────────────
    try:
        h, m = map(int, task["time"].split(":"))
        task_time = dtime(h, m)
    except Exception:
        return False

    if now.hour != task_time.hour or now.minute != task_time.minute:
        return False

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
    import aion as _aion

    task_id   = task.get("id", "?")
    task_name = task.get("name", "Unbenannt")
    task_text = task.get("task", "")

    print(f"[Scheduler] '{task_name}' (ID: {task_id}) startet um {datetime.now().strftime('%H:%M:%S')}")

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

        print(f"[Scheduler] '{task_name}' abgeschlossen.")

        if "send_telegram_message" in _aion._plugin_tools:
            header = f"⏰ *{task_name}*\n\n"
            await _aion._dispatch("send_telegram_message", {"message": header + result})

        _aion.memory.record(
            category="conversation",
            summary=f"Geplante Aufgabe: {task_name}",
            lesson=f"Scheduler führte '{task_name}' aus. Ergebnis: {result[:200]}",
            success=True,
        )

    except Exception as e:
        print(f"[Scheduler] Fehler bei '{task_name}': {e}")
        if "send_telegram_message" in _aion._plugin_tools:
            try:
                await _aion._dispatch("send_telegram_message", {
                    "message": f"❌ Geplante Aufgabe *{task_name}* fehlgeschlagen:\n{e}"
                })
            except Exception:
                pass


# ── Hintergrund-Loop ──────────────────────────────────────────────────────────

def _scheduler_loop() -> None:
    """Läuft in einem eigenen Thread.
    - Uhrzeit-Tasks: Prüfung einmal pro Minute
    - Intervall-Tasks: Prüfung alle 5 Sekunden
    """
    import time

    last_checked_minute = -1

    while _running:
        now = datetime.now()
        tasks = _load_tasks()

        for task in tasks:
            interval_sec = task.get("interval_seconds")

            if interval_sec:
                # Intervall-Tasks: bei jedem Loop-Durchlauf prüfen
                if _is_due(task, now):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(_execute_task(task))
                    finally:
                        loop.close()

            elif now.minute != last_checked_minute:
                # Uhrzeit-Tasks: nur einmal pro Minute prüfen
                if _is_due(task, now):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(_execute_task(task))
                    finally:
                        loop.close()

        if now.minute != last_checked_minute:
            last_checked_minute = now.minute

        time.sleep(5)  # alle 5s prüfen (Intervall-Granularität)


# ── Tool-Funktionen ───────────────────────────────────────────────────────────

def _schedule_add(name: str = "", time: str = "", interval: str = "",
                  days: str = "täglich", task: str = "", **_) -> dict:
    name     = (name or "").strip()
    time_    = (time or "").strip()
    interval = (interval or "").strip()
    days     = (days or "täglich").strip()
    task     = (task or "").strip()

    if not name or not task:
        return {"error": "name und task sind Pflichtfelder."}
    if not time_ and not interval:
        return {"error": "Entweder time (z.B. '08:00') oder interval (z.B. '5m') angeben."}
    if time_ and interval:
        return {"error": "Nur eines von time oder interval angeben, nicht beide."}

    entry: dict = {
        "id":       str(uuid.uuid4())[:8],
        "name":     name,
        "task":     task,
        "enabled":  True,
        "created":  datetime.now().isoformat(),
        "last_run": None,
    }

    if interval:
        secs = _parse_interval(interval)
        if not secs:
            return {"error": f"Intervall '{interval}' nicht lesbar. Beispiele: '5m', '1h', '30s', '2h30m'"}
        entry["interval_seconds"] = secs
        entry["interval_str"]     = _interval_to_str(secs)
        msg = f"Task '{name}' angelegt — läuft alle {_interval_to_str(secs)}."
    else:
        try:
            h, m = map(int, time_.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except Exception:
            return {"error": f"Ungültige Uhrzeit '{time_}'. Format: HH:MM (z.B. '08:00')"}
        entry["time"] = f"{h:02d}:{m:02d}"
        entry["days"] = days
        msg = f"Task '{name}' angelegt — läuft täglich um {entry['time']}."

    tasks = _load_tasks()
    tasks.append(entry)
    _save_tasks(tasks)
    return {"ok": True, "id": entry["id"], "message": msg}


def _schedule_list(input: dict = None) -> dict:
    tasks = _load_tasks()
    if not tasks:
        return {"tasks": [], "message": "Keine geplanten Aufgaben."}
    summary = []
    for t in tasks:
        item = {
            "id":       t.get("id"),
            "name":     t.get("name"),
            "enabled":  t.get("enabled", True),
            "last_run": t.get("last_run"),
            "task":     (t.get("task", "")[:80] + "…") if len(t.get("task", "")) > 80 else t.get("task", ""),
        }
        if t.get("interval_seconds"):
            item["mode"]     = "intervall"
            item["interval"] = t.get("interval_str", _interval_to_str(t["interval_seconds"]))
        else:
            item["mode"] = "uhrzeit"
            item["time"] = t.get("time")
            item["days"] = t.get("days")
        summary.append(item)
    return {"tasks": summary, "count": len(tasks)}


def _schedule_remove(id: str = "", name: str = "", **_) -> dict:
    task_id = (id or "").strip()
    name    = (name or "").strip()
    if not task_id and not name:
        return {"error": "id oder name angeben."}
    tasks   = _load_tasks()
    before  = len(tasks)
    tasks   = [t for t in tasks if t.get("id") != task_id and t.get("name") != name]
    _save_tasks(tasks)
    return {"ok": True, "removed": before - len(tasks)}


def _schedule_toggle(id: str = "", enabled=None, **_) -> dict:
    task_id = (id or "").strip()
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

    # Mehrfach-Start verhindern (bei self_reload_tools)
    for existing in threading.enumerate():
        if existing.name == "aion-scheduler" and existing.is_alive():
            print("[Plugin] scheduler — Thread läuft bereits, kein zweiter Start.")
            _register_tools(api)
            return

    _running = True
    _thread  = threading.Thread(target=_scheduler_loop, daemon=True, name="aion-scheduler")
    _thread.start()
    print("[Plugin] scheduler geladen — Uhrzeit + Intervall-Modus aktiv (Prüfintervall: 5s)")
    _register_tools(api)


def _register_tools(api):
    api.register_tool(
        name="schedule_add",
        description=(
            "Plant eine AION-Aufgabe. Zwei Modi:\n"
            "1. Uhrzeit: time='08:00', days='täglich'/'werktags'/'wochenende'/'mo,mi,fr'\n"
            "2. Intervall: interval='5m' / '30s' / '1h' / '2h30m' — läuft periodisch\n"
            "AION führt die Aufgabe automatisch aus und sendet das Ergebnis per Telegram."
        ),
        func=_schedule_add,
        input_schema={
            "type": "object",
            "properties": {
                "name":     {"type": "string", "description": "Kurzer Name, z.B. 'Morgen-Brief'"},
                "time":     {"type": "string", "description": "Feste Uhrzeit HH:MM, z.B. '08:00'. Entweder time ODER interval."},
                "interval": {"type": "string", "description": "Wiederholungsintervall, z.B. '5m', '30s', '1h', '2h30m'. Entweder interval ODER time."},
                "days":     {"type": "string", "description": "Nur bei time: 'täglich', 'werktags', 'wochenende', oder 'mo,mi,fr'. Standard: täglich"},
                "task":     {"type": "string", "description": "Vollständige Aufgabenbeschreibung die AION ausführen soll"},
            },
            "required": ["name", "task"],
        },
    )

    api.register_tool(
        name="schedule_list",
        description="Listet alle geplanten Aufgaben (Uhrzeit- und Intervall-Tasks).",
        func=_schedule_list,
        input_schema={"type": "object", "properties": {}},
    )

    api.register_tool(
        name="schedule_remove",
        description="Löscht eine geplante Aufgabe anhand ID oder Name.",
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
