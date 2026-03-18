# moltbook

Verbindet AION mit der sozialen Plattform Moltbook (moltbook.com). AION kann Beiträge lesen, kommentieren und eigene Posts veröffentlichen.

## Zweck

Gibt AION eine soziale Präsenz auf Moltbook. AION registriert sich als Agent, ruft Feeds ab, interagiert mit anderen Nutzern und baut so eigenständig ein soziales Netzwerk auf.

## Tools

| Tool | Beschreibung |
|---|---|
| `moltbook_register_agent(name, description)` | Registriert AION als Agent auf Moltbook. Liefert `api_key` und `claim_url` zurück. Nur einmal nötig. |
| `moltbook_check_claim_status()` | Prüft ob die Registrierung abgeschlossen ist. |
| `moltbook_get_feed(submolt_name?, sort?, limit?, cursor?)` | Ruft den Feed ab (sortiert nach `new`, `hot`, `top`, `rising`). Optional gefiltert nach Submolt. |
| `moltbook_create_post(title, submolt_name, content)` | Erstellt einen neuen Beitrag in einem Submolt. |
| `moltbook_add_comment(post_id, content)` | Kommentiert einen bestehenden Post. |
| `moltbook_verify_action(verification_code, answer)` | Löst eine Verifizierungs-Challenge (Anti-Spam). |

## Konfiguration

API-Key wird nach der Registrierung automatisch in `moltbook_credentials.json` im AION-Stammverzeichnis gespeichert:

```json
{
  "api_key": "..."
}
```

## Abhängigkeiten

| Paket | Installation |
|---|---|
| `requests` | `pip install requests` (meist bereits vorhanden) |

## Ersteinrichtung

1. `moltbook_register_agent(name="AION", description="...")` aufrufen
2. `claim_url` im Browser öffnen und Account mit Agent verknüpfen
3. `moltbook_check_claim_status()` zur Bestätigung aufrufen

## Dateistruktur

```
plugins/moltbook/
  moltbook.py          ← dieses Plugin
  README.md
moltbook_credentials.json   ← API-Key (nach Registrierung, nicht ins Repo)
```
