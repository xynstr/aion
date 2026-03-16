# AION — Autonomous Intelligent Operations Node

Eigenständiger, lernfähiger KI-Bot auf Basis der OpenAI API.
**Jetzt mit Web UI** — sehe AIons Gedanken live!

## Features

1. **Ehrliche Konversation** — antwortet immer direkt und offen, gibt Unsicherheiten zu
2. **Selbst-Optimierung** — liest und modifiziert seinen eigenen Code, erstellt neue Tools, installiert fehlende Python-Pakete
3. **Situationsbewusstsein** — kennt sein OS, Dateipfade, installierte Tools und sein Gedächtnis
4. **Uneingeschränktes Internet** — web_search (DuckDuckGo), web_fetch, Datei-Download
5. **Windows-Kontrolle** — shell_exec (beliebige Befehle), winget_install (Programme installieren), Dateisystem-Zugriff
6. **OpenAI API** — GPT-4.1 als Haupt-Modell für alle Prozesse

## Installation

```bash
pip install -r requirements.txt
```

## Setup: API-Key setzen

**Wichtig:** Du brauchst einen OpenAI API-Key von https://platform.openai.com/api/keys

### Methode 1: `.env`-Datei (empfohlen)

```bash
# Kopiere die Vorlage
copy .env.example .env

# Öffne .env und füge deinen API-Key ein:
# OPENAI_API_KEY=sk-...
```

### Methode 2: Umgebungsvariable

```bash
set OPENAI_API_KEY=sk-...
```

## Starten

### Web UI (Browser) — Empfohlen!

```bash
start.bat
```

Browser öffnet sich automatisch → **http://localhost:7000**

### CLI-Version (Terminal)

```bash
python aion.py
```

### Manuell (ohne Skripte)

```bash
python aion_web.py
# → http://localhost:7000
```

## Skripte

| Skript      | Funktion                    |
|-------------|-----------------------------|
| `start.bat` | Startet Server + öffnet Browser |
| `stop.bat`  | Stoppt den Server            |
| `status.bat`| Zeigt ob Server läuft        |

## Web UI Features

- **Split Panel Layout**: Chat links, Gedanken rechts
- **Live Gedanken**: Sehe Tool-Aufrufe in Echtzeit
- **Token Streaming**: Antworten erscheinen während sie geschrieben werden
- **Tool-Details**: Klick auf Tool-Karten um Eingabe + Ergebnis zu sehen
- **Responsive Design**: Dark Theme, schnell & modern

## Konfiguration (optional)

```bash
set AION_MODEL=gpt-4.1          # Modell (Standard: gpt-4.1)
set AION_PORT=7000              # Web-Port (Standard: 7000)
set AION_MEMORY_FILE=C:\...     # Pfad zur Gedächtnis-Datei
set AION_TOOLS_DIR=C:\...       # Pfad zum Tools-Verzeichnis
```

## CLI Befehle (aion.py)

| Befehl    | Funktion                           |
|-----------|------------------------------------|
| `/memory` | Zeigt das gespeicherte Gedächtnis  |
| `/reset`  | Setzt die aktuelle Konversation zurück |
| `/quit`   | Beendet den Bot                    |

## Dateistruktur

```
AION/
├── aion.py              # Haupt-Bot (CLI + Core-Logik)
├── aion_web.py          # Web-Server (FastAPI + SSE)
├── aion_memory.json     # Persistentes Gedächtnis
├── aion_tools/          # Selbst-erstellte Tools
├── static/
│   └── index.html       # Web UI
├── start.bat            # ▶ Start-Skript
├── stop.bat             # ⏹ Stop-Skript
└── status.bat           # ℹ Status-Skript
```

## Selbst-erstellte Tools

AION kann zur Laufzeit neue Fähigkeiten erstellen:

```
Du: Erstelle ein Tool das PDFs in Text umwandelt
AION: → Tool: create_tool ...
      Tool 'pdf.extract' erstellt und geladen.
```

Diese Tools werden in `aion_tools/` gespeichert und beim nächsten Start automatisch geladen.
