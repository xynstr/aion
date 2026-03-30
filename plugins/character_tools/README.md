# character_tools

Direkter Lese- und Schreibzugriff auf `character.md` — AIONs Persönlichkeitsdatei.

## Tools

| Tool | Beschreibung |
|------|-------------|
| `character_read()` | Vollständigen Inhalt von character.md zurückgeben |
| `character_update_section(section, content)` | Einen Abschnitt nach Name ersetzen (wird angelegt falls nicht vorhanden) |
| `character_append_insight(insight)` | Eintrag in "My insights" anhängen — schnell, ohne vorheriges Lesen |
| `character_set_user_knowledge(content)` | Abschnitt "What I know about my user" komplett ersetzen |

## Wann nutzen

- Immer wenn du etwas Neues über den Nutzer lernst → `character_set_user_knowledge`
- Immer wenn dir etwas an dir selbst auffällt → `character_append_insight`
- Um einen beliebigen Abschnitt zu aktualisieren → `character_update_section`
- Zum Lesen vor größeren Überarbeitungen → `character_read`

Änderungen werden sofort wirksam — der System-Prompt-Cache wird automatisch invalidiert.
