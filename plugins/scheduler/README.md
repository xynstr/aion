# scheduler

Cron-ähnlicher Aufgaben-Planer für AION. Zwei Modi: feste Uhrzeiten und Intervalle.

## Zweck

AION führt Aufgaben automatisch aus — zu festen Uhrzeiten oder in regelmäßigen Abständen. Das Ergebnis jeder Aufgabe wird automatisch per Telegram gesendet (wenn konfiguriert).

## Tools

| Tool | Beschreibung |
|---|---|
| `schedule_add(name, task, time?, interval?, days?)` | Neue Aufgabe anlegen. Entweder `time` (feste Uhrzeit) oder `interval` (Wiederholung) angeben. |
| `schedule_list()` | Alle Aufgaben anzeigen mit Modus, Zeit/Intervall, letztem Lauf. |
| `schedule_remove(id?, name?)` | Aufgabe löschen. |
| `schedule_toggle(id, enabled?)` | Aufgabe aktivieren/deaktivieren. |

## Modi

### Uhrzeit-Modus
```
schedule_add(name="Morgen-Brief", time="08:00", days="werktags",
             task="Lies meine Emails und schreib mir eine Zusammenfassung.")
```

| Parameter | Werte |
|---|---|
| `time` | `"HH:MM"` — z.B. `"08:00"`, `"23:30"` |
| `days` | `"täglich"` (Standard), `"werktags"`, `"wochenende"`, `"mo,mi,fr"` |

### Intervall-Modus
```
schedule_add(name="5-Minuten-Ping", interval="5m",
             task="Schreibe mir eine kurze motivierende Nachricht auf Telegram.")
```

| Beispiel | Bedeutung |
|---|---|
| `"30s"` | alle 30 Sekunden |
| `"5m"` | alle 5 Minuten |
| `"1h"` | jede Stunde |
| `"2h30m"` | alle 2 Stunden 30 Minuten |
| `"alle 10 Minuten"` | alle 10 Minuten (natürliche Sprache) |

## Wie es funktioniert

- Scheduler-Thread läuft im Hintergrund, prüft alle **5 Sekunden**
- Intervall-Tasks: Ausführung wenn `jetzt - letzter_Lauf >= Intervall`
- Uhrzeit-Tasks: Ausführung einmal pro Tag zur eingestellten Zeit
- Ergebnis wird via `send_telegram_message` gesendet
- Doppelausführung verhindert: `last_run` wird sofort beim Start gesetzt

## Persistenz

Tasks werden in `plugins/scheduler/tasks.json` gespeichert.

## Dateistruktur

```
plugins/scheduler/
  scheduler.py    ← dieses Plugin
  tasks.json      ← gespeicherte Tasks (auto-generiert)
  README.md
```
