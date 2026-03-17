# AION — Autonomous Intelligent Operations Node

Ein autonomer KI-Agent für Windows. Läuft als Python-Prozess, kommuniziert über OpenAI- oder Google Gemini-API, führt Tools aus, lernt und kann sich selbst modifizieren.

---

## Features

- **Autonomes Arbeiten** — loop bis zu 20 Tool-Iterationen ohne Nutzer-Warten
- **Selbst-Modifikation** — liest, patcht und überschreibt eigenen Code; erstellt neue Plugins
- **Web UI** — Live-Stream von Antworten, Gedanken (Reflexionen) und Tool-Aufrufen
- **Telegram** — bidirektionale Anbindung über Telegram Bot (bidirektional, 1 Plugin-Datei)
- **Gedächtnis** — persistentes JSON-Gedächtnis + Konversationshistorie (JSONL)
- **Multi-Provider** — OpenAI (GPT-4.1, o3 u.a.) und Google Gemini (2.5-pro, 2.5-flash u.a.) wechselbar
- **Plugin-System** — jede `.py`-Datei in `plugins/` wird automatisch geladen
- **CLIO-Reflexion** — Konfidenz-Check und Gedanken-Protokoll nach jeder Nutzer-Nachricht

---

## Voraussetzungen

- Python 3.10+
- Windows (für `shell_exec`, `winget_install`)
- OpenAI API-Key und/oder Google Gemini API-Key

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Konfiguration

Erstelle eine `.env`-Datei im Projektverzeichnis (Vorlage: `.env.example`):

```env
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
TELEGRAM_BOT_TOKEN=1234567890:AAE...   # optional
TELEGRAM_CHAT_ID=123456789             # optional
AION_MODEL=gpt-4.1                     # optional, default: gpt-4.1
AION_PORT=7000                         # optional, default: 7000
```

Das aktive Modell wird in `config.json` gespeichert und beim nächsten Start wiederhergestellt.

---

## Starten

### Web UI (empfohlen)

```bash
start.bat
```

Öffnet automatisch `http://localhost:7000`

### Manuell

```bash
python aion_web.py     # Web-Server (Port 7000)
python aion.py         # CLI-Modus
```

---

## Web UI

- **Chat** (links): Eingabe und Antworten mit Token-Streaming
- **Gedanken** (rechts, Tab 1): AIons Reflexionen — nach jeder Nachricht automatisch sichtbar
- **Tools** (rechts, Tab 2): Tool-Aufrufe mit Ein- und Ausgabe — nur bei Klick aufgeklappt
- **Modell-Wechsel**: Dropdown oben rechts — wechselt sofort und persistiert in `config.json`

---

## Dateisystem

```
AION/
├── aion.py                  # Kernlogik: Memory, Tools, LLM-Loop, CLI
├── aion_web.py              # Web-Server (FastAPI + SSE), Port 7000
├── plugin_loader.py         # Lädt alle Plugins aus plugins/
├── static/
│   └── index.html           # Web UI (Vanilla JS)
├── plugins/
│   ├── telegram_bot.py      # Telegram-Bot (einzige Telegram-Datei)
│   ├── gemini_provider.py   # Google Gemini + switch_model Tool
│   ├── memory_plugin.py     # Konversationshistorie (JSONL)
│   ├── clio_reflection.py   # CLIO-Konfidenz-Check
│   ├── todo_tools.py        # Aufgabenverwaltung
│   ├── smart_patch.py       # Fuzzy-Code-Patching
│   ├── heartbeat.py         # Keep-Alive
│   └── restart_tool.py      # Neustart-Plugin
├── character.md             # Persönlichkeit (selbst-aktualisierend)
├── AION_SELF.md             # Selbst-Dokumentation (Tools, Struktur, API)
├── aion_memory.json         # Persistentes Gedächtnis (max. 300 Einträge)
├── thoughts.md              # Aufgezeichnete Gedanken
├── .env                     # API-Keys (nicht in Git)
├── config.json              # Aktives Modell (persistiert)
├── start.bat                # Startet Server + Browser
├── stop.bat                 # Stoppt den Server
└── status.bat               # Zeigt ob Server läuft
```

---

## CLI-Befehle (`aion.py`)

| Befehl | Funktion |
|--------|----------|
| `/memory` | Gespeichertes Gedächtnis anzeigen |
| `/reset` | Aktuelle Konversation zurücksetzen |
| `/model <name>` | Aktives Modell wechseln |
| `/quit` | Beendet den Bot |

---

## Verfügbare Modelle

| Provider | Modell | Empfehlung |
|---------|--------|-----------|
| Google Gemini | `gemini-2.5-pro` | Beste Qualität |
| Google Gemini | `gemini-2.5-flash` | Schnell & günstig |
| Google Gemini | `gemini-2.0-flash` | Stabil |
| OpenAI | `gpt-4.1` | OpenAI Flagship |
| OpenAI | `gpt-4o` | Multimodal |
| OpenAI | `o3` | Reasoning |
| OpenAI | `o4-mini` | Schnell |

Wechsel per Web UI (Dropdown) oder CLI: `/model gemini-2.5-pro`

---

## Plugin erstellen

Jede Datei in `plugins/` muss eine `register(api)`-Funktion exportieren:

```python
def register(api):
    def mein_tool(param: str) -> dict:
        return {"ok": True, "result": param}

    api.register_tool(
        name="mein_tool",
        description="Beschreibung für das LLM",
        func=mein_tool,
        input_schema={
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "..."}
            },
            "required": ["param"]
        }
    )
```

Neue Plugins werden sofort geladen — kein Neustart nötig (außer bei Änderungen an `aion.py`).

AION kann auch zur Laufzeit Plugins via `create_plugin` Tool erstellen.

---

## Telegram

1. Bot bei [@BotFather](https://t.me/BotFather) erstellen → Token
2. `TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID` in `.env` setzen
3. AION starten — Telegram-Polling startet automatisch

---

## Sicherheitshinweis

- `.env` ist in `.gitignore` — API-Keys niemals committen
- `shell_exec` führt beliebige Windows-Befehle aus — nur auf vertrauenswürdigen Systemen einsetzen
- `self_modify_code` / `self_patch_code` — AION kann seinen eigenen Code ändern
