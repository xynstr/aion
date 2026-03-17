# image_search Plugin

Sucht Bilder zu einem Suchbegriff und gibt direkte Bild-URLs zurück.

## Strategie

1. **Primär**: `duckduckgo-search` — schnell, kein Browser
2. **Fallback**: Playwright (Chromium headless) — robust wenn DDG Rate-Limiting greift

## Installation

```bash
pip install duckduckgo-search
pip install playwright && playwright install chromium
```

## Tool

| | |
|---|---|
| **Name** | `image_search` |
| **Parameter** | `query` (string, required), `count` (int, default 3) |
| **Rückgabe** | `{"ok": true, "images": [{"url": "...", "title": "..."}]}` |

## Hinweise

- Englische Suchbegriffe liefern bessere Ergebnisse
- AION zeigt die Bilder automatisch im UI — kein Markdown `![]()` nötig
- Wird automatisch geladen wenn `AION_PLUGINS_DIR/image_search/` existiert
