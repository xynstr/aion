# Plugin: memory_plugin

**Konversations-Historie und Gedächtnis**

## Funktion

Speichert alle Nachrichten (User und AION) in einer Konversationshistorie mit Timestamps. Erlaubt Abruf der letzten N Nachrichten für Kontext.

## Tools

### `memory_append_history`

**Parameter:**
- `role` (string): "user" oder "assistant"
- `content` (string): Nachrichtentext

**Ausgabe:**
- `ok` (boolean): Erfolgreich gespeichert?

### `memory_read_history`

**Parameter:**
- `num_entries` (int, optional): Anzahl Einträge (default: 50)

**Ausgabe:**
- `entries` (array): Letzte N Einträge mit role, content, timestamp
- `error` (string): Fehlermeldung falls Problem

## Speicherort

- `conversation_history.jsonl`: Eine JSON-Zeile pro Eintrag (im Hauptverzeichnis)

## Funktionsweise

1. Jede Nachricht wird automatisch mit Timestamp gespeichert
2. JSONL-Format: eine komplette Zeile pro Eintrag (leicht zu streamen)
3. Ermöglicht längerfristiges Gedächtnis zwischen Sessions

## Format

```json
{"role": "user", "content": "Hallo AION", "ts": "2026-03-17T15:20:30.123456"}
{"role": "assistant", "content": "Hallo! Wie kann ich dir helfen?", "ts": "2026-03-17T15:20:31.234567"}
```
