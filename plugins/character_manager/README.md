# Character Manager

Verwaltet AION's Persönlichkeit und Charaktermerkmale.

## Features

- **Datei**: `character.md` im AION-Hauptverzeichnis
- **Hot-Reload**: Änderungen sofort verfügbar, kein Neustart nötig
- **Selbstlernend**: AION kann seine eigene Persönlichkeit updaten

## Tools

| Tool | Beschreibung |
|------|-------------|
| `update_character(section, content)` | Aktualisiert einen Charakterabschnitt |

## Charakterabschnitte

AION pflegt folgende Persönlichkeitssektionen:

- **nutzer**: Was ich über meinen User weiß
- **erkenntnisse**: Meine Erkenntnisse über mich selbst
- **verbesserungen**: Dinge, die ich verbessern will
- **auftreten**: Wie ich auftreten will
- **humor**: Mein Humor & Stil

## Verwendung

Sag zu AION:
- *"Speichere in meinem Charakter: Ich mag Sarcasmus und formale Sprache"*
- *"Update: Ich sollte prägnantere Antworten geben"*

AION wird diese Infos dann in `character.md` speichern und bei zukünftigen Antworten beachten.
