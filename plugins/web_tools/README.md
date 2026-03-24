# Web Tools

Web-Suche und -Abruf: Recherchiere aktuelle Informationen aus dem Internet.

## Features

- **Primär**: DuckDuckGo (ddgs-Bibliothek — aktiv gegen Bot-Blocking)
- **Fallback**: httpx-Scraping als Backup
- **Schnell**: Optimiert für niedrige Latenz
- **Sicher**: Keine JavaScript-Ausführung

## Tools

| Tool | Beschreibung |
|------|-------------|
| `web_search(query, max_results)` | Sucht DuckDuckGo nach Ergebnissen |
| `web_fetch(url, prompt)` | Lädt Seite und verarbeitet Inhalt |

## Verwendung

Sag zu AION:
- *"Suche nach aktuellen Python-Framework-Trends 2026"*
- *"Lade https://example.com und fasse den Hauptinhalt zusammen"*

AION wird dann:
1. `web_search()` aufrufen um aktuelle Ergebnisse zu finden
2. Relevante Links mit `web_fetch()` öffnen
3. Ergebnisse verarbeiten und zusammenfassen

## Search-Parameter

- `query` (string, required) — Suchtext
- `max_results` (int, optional, default: 8) — Anzahl Ergebnisse

## Fetch-Parameter

- `url` (string, required) — URL zum Laden
- `prompt` (string, required) — Was auf der Seite gesucht/analysiert werden soll

## Beispiel-Output

```json
{
  "results": [
    {
      "title": "...",
      "url": "...",
      "snippet": "..."
    }
  ]
}
```

## Limits

- Timeout: 10 Sekunden pro Fetch
- Max. Seitengröße: 5 MB
- Keine JavaScript-Verarbeitung (statische HTML nur)
