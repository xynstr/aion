# Plugin: docx_tool

**Erstelle Microsoft Word-Dokumente (.docx)**

## Funktion

Erlaubt AION, Word-Dokumente (.docx) zu erstellen und zu speichern. Nützlich für Reports, Briefe, Dokumentation und alle Aufgaben, die formatierte Textausgabe benötigen.

## Tool: `create_docx`

**Parameter:**
- `path` (string, erforderlich): Vollständiger Pfad zur neuen .docx-Datei
- `content` (string, optional): Textinhalt als Paragraph

**Ausgabe:**
- `ok` (boolean): Erfolgreich gespeichert?
- `path` (string): Pfad zur erstellten Datei
- `error` (string): Fehlermeldung falls Problem

## Funktionsweise

1. Neues Word-Dokument erstellen
2. Inhalt als Paragraph hinzufügen
3. Unter dem angegebenen Pfad speichern

## Installation

```bash
pip install python-docx
```

## Beispiel

```
AION erstellt Brief: create_docx(
  path="C:/Briefe/angebot.docx",
  content="Sehr geehrte Damen und Herren..."
)
→ angebot.docx wird gespeichert
```
