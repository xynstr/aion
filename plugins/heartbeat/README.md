# Plugin: heartbeat

**Keep-Alive Monitoring und Health Check**

## Funktion

Sendet periodisch Heartbeat-Signale um zu zeigen, dass AION noch läuft. Nützlich zum Überwachen der Prozess-Gesundheit und zur Problemerkennung.

## Tool: `heartbeat_last`

**Parameter:** keine

**Ausgabe:**
- `last_heartbeat` (string): Zeitstempel des letzten Heartbeats
- `error` (string): Falls Problem beim Lesen

## Funktionsweise

1. **Automatisch**: Im Hintergrund läuft ein Daemon-Thread
2. **Intervall**: Alle 60 Sekunden wird ein Timestamp geschrieben
3. **Log**: Alle Heartbeats landen in `plugins/heartbeat/heartbeat.log`
4. **Tool**: `heartbeat_last` zeigt den neuesten Heartbeat

## Datei

- `heartbeat.log`: Alle Heartbeats mit Timestamps (im Plugin-Ordner)

## Beispiel

```
heartbeat_last()
→ "Heartbeat: 2026-03-17T15:23:45.123456"
```

Zeigt dass AION aktiv war (zuletzt 15:23:45).
