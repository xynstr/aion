# scheduler

Cron-ähnlicher Aufgaben-Planer für AION. Führt beliebige AION-Aufgaben automatisch zu festgelegten Zeiten aus.

## Zweck

AION kann damit eigenständig täglich wiederkehrende Aufgaben erledigen — ohne dass der Nutzer aktiv sein muss. Das Ergebnis jeder Aufgabe wird automatisch per Telegram gesendet.

## Tools

| Tool | Beschreibung |
|---|---|
| `schedule_add(name, time, task, days?)` | Legt eine neue geplante Aufgabe an. `task` ist eine vollständige AION-Aufgabenbeschreibung. |
| `schedule_list()` | Zeigt alle geplanten Aufgaben mit ID, Uhrzeit, letztem Lauf. |
| `schedule_remove(id?, name?)` | Löscht eine Aufgabe anhand ID oder Name. |
| `schedule_toggle(id, enabled?)` | Aktiviert oder deaktiviert eine Aufgabe ohne sie zu löschen. |

## Parameter

**`schedule_add`:**
- `name` — Kurzer Name, z.B. `"Morgen-Brief"`
- `time` — Uhrzeit im Format `HH:MM`, z.B. `"08:00"`
- `task` — Vollständige Aufgabe wie eine Nutzer-Nachricht, z.B. `"Prüfe den Moltbook-Feed und kommentiere interessante Posts"`
- `days` — `"täglich"` (Standard), `"werktags"`, `"wochenende"`, oder Komma-Liste wie `"mo,mi,fr"`

## Wie es funktioniert

- Der Scheduler-Thread läuft im Hintergrund und prüft alle 10 Sekunden ob Tasks fällig sind
- Fällige Tasks werden mit einer eigenen `AionSession(channel="scheduler")` ausgeführt
- Das Ergebnis wird via `send_telegram_message` gesendet (wenn Telegram konfiguriert)
- Jeder Task läuft pro Tag maximal einmal (verhindert Doppelausführung bei Neustart)

## Persistenz

Tasks werden in `plugins/scheduler/tasks.json` gespeichert und überleben Neustarts.

## Dateistruktur

```
plugins/scheduler/
  scheduler.py    ← dieses Plugin
  tasks.json      ← gespeicherte Tasks (wird automatisch erstellt)
  README.md
```

## Beispiele

```
schedule_add(
  name="Morgen-Briefing",
  time="07:30",
  days="werktags",
  task="Lies die neuesten Moltbook-Posts, erstelle eine Zusammenfassung der interessantesten Diskussionen und sende sie mir."
)

schedule_add(
  name="Nacht-Reflexion",
  time="23:00",
  days="täglich",
  task="Reflektiere über den heutigen Tag, schreibe einen Gedanken in thoughts.md und update character.md wenn du etwas Neues über dich gelernt hast."
)
```
