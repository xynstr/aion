# Plugin: pid_tool

**Prozess-ID Abfrage**

## Funktion

Gibt die Prozess-ID (PID) des aktuell laufenden AION-Prozesses zurück. Nützlich für Debugging und Prozess-Verwaltung.

## Tool: `get_own_pid`

**Parameter:** keine

**Ausgabe:**
- `ok` (boolean): Immer true
- `pid` (int): Prozess-ID von AION

## Funktionsweise

Nutzt `os.getpid()` um die PID des aktuellen Python-Prozesses zu bekommen.

## Verwendungsbeispiel

```
AION ruft: get_own_pid()
→ {"ok": true, "pid": 12345}

Nutzer kann dann z.B.:
tasklist /PID 12345 (Windows)
kill 12345 (Linux/Mac)
```

## Wofür nützlich?

- Debugging: Welcher Prozess ist AION?
- Monitoring: Prozess überwachen/konfigurieren
- Automation: Externe Tools können AION-Prozess identifizieren
- Multi-Instance: Falls mehrere AION läuft → welche ist welche?
