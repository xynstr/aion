# Plugin: todo_tools

**Aufgabenverwaltung und Todo-Listen**

## Funktion

Verwaltet eine persistente To-Do-Liste als JSON-Datei. Erlaubt AION, Aufgaben zu erstellen, aufzulisten und zu löschen.

## Tools

### `todo_add`

**Parameter:**
- `task` (string): Aufgabenbeschreibung
- `created` (string, optional): Erstellungsdatum

**Ausgabe:**
- `ok` (boolean): Erfolgreich hinzugefügt?
- `task` (string): Die hinzugefügte Aufgabe

### `todo_list`

**Parameter:** keine

**Ausgabe:**
- `todos` (array): Alle Aufgaben mit task und created

### `todo_remove`

**Parameter:**
- `task` (string): Aufgabenbeschreibung (muss exakt passen)

**Ausgabe:**
- `ok` (boolean): Erfolgreich entfernt?
- `removed` (string): Die entfernte Aufgabe

## Speicherort

- `plugins/todo_tools/todo_list.json`: Alle Aufgaben

## Format

```json
[
  {"task": "Code testen", "created": "2026-03-17T10:00:00"},
  {"task": "Dokumentation schreiben", "created": "2026-03-17T11:30:00"}
]
```

## Beispiel

```
AION: "Füge eine Aufgabe hinzu"
→ todo_add(task="Web UI redesign", created="2026-03-17")

AION: "Was steht auf meiner Todo-Liste?"
→ todo_list()
→ ["Web UI redesign", "Database optimization", ...]

AION: "Entferne erledigte Aufgaben"
→ todo_remove(task="Database optimization")
```
