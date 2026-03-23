# playwright_browser

Browser-Steuerung via Playwright (Chromium).

## Einrichtung

```bash
pip install playwright
playwright install chromium
```

## Tools

| Tool | Beschreibung |
|------|-------------|
| `browser_open(url)` | URL laden |
| `browser_screenshot()` | Screenshot als Base64-PNG |
| `browser_click(selector)` | Element klicken |
| `browser_fill(selector, value)` | Eingabefeld befüllen |
| `browser_get_text()` | Seitentext abrufen (max. 10.000 Zeichen) |
| `browser_evaluate(js)` | JavaScript ausführen |
| `browser_find(selector)` | Elemente suchen |
| `browser_close()` | Seite schließen |

## Configuration

`config.json`:
```json
{
  "browser_headless": true
}
```

`false` = sichtbares Browserfenster (gut zum Debugging).
