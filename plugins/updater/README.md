# Updater

Automatischer GitHub-Release-Check und Update-Benachrichtigungen.

## Features

- **Täglicher Check**: Prüft automatisch einmal pro Tag auf neue Releases
- **Multi-Channel**: Benachrichtigungen via Telegram, Discord, Slack
- **Version-Tracking**: Zeigt aktuelle vs. verfügbare Version
- **Web-UI Integration**: Status im System-Tab sichtbar

## Konfiguration

Setze in `.env`:
```
AION_GITHUB_REPO=owner/repo-name
# z.B. AION_GITHUB_REPO=xynstr/aion
```

## Tools

| Tool | Beschreibung |
|------|-------------|
| `check_for_updates()` | Manuell GitHub auf neue Version prüfen |
| `update_status()` | Zeigt aktuelle Update-Status |

## Timing

- **Erster Check**: 60 Sekunden nach AION-Start
- **Weitere Checks**: Alle 24 Stunden
- **Timeout**: 10 Sekunden pro GitHub-Abfrage

## Benachrichtigungen

Wenn eine neue Version verfügbar ist:
- **Telegram**: Bot-Nachricht mit Release-Link
- **Discord**: Channel-Nachricht mit Version-Info
- **Slack**: Team-Benachrichtigung
- **Web-UI**: Gelbes Banner im System-Tab

## Web-APIs

| Endpoint | Beschreibung |
|----------|-------------|
| `GET /api/update-status` | Aktueller Update-Status (JSON) |
| `POST /api/update-trigger` | Erzwingt sofortigen Check |

## Anleitung zum Update

Wenn eine neue Version verfügbar ist:
```bash
aion update
```

Dies führt `git pull` + `pip install -e .` aus.
