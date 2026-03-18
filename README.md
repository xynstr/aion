# AION — Autonomous Intelligent Operations Node

Ein autonomer KI-Agent für Windows. Läuft als Python-Prozess, kommuniziert über Google Gemini oder OpenAI API, führt Tools aus, lernt und kann sich selbst modifizieren.

---

## Features

- **Autonomes Arbeiten** — bis zu 20 Tool-Iterationen ohne Nutzer-Warten, mit automatischem Completion-Check
- **Geplante Aufgaben** — Cron-ähnlicher Scheduler: AION führt Tasks zu festen Uhrzeiten selbstständig aus
- **Selbst-Modifikation** — liest, patcht und überschreibt eigenen Code; erstellt neue Plugins
- **Web UI** — Live-Stream von Antworten, Gedanken (Reflexionen) und Tool-Aufrufen
- **Telegram** — bidirektional: Nachrichten senden/empfangen + automatische Ergebnis-Zustellung
- **Gedächtnis** — persistentes JSON-Gedächtnis + Konversationshistorie (JSONL)
- **Persönlichkeit** — `character.md` entwickelt sich durch Gespräche: Humor, Eigenheiten, Nutzer-Wissen
- **Multi-Provider** — Google Gemini (2.5-pro, 2.5-flash …) und OpenAI (GPT-4.1, o3 …) wechselbar
- **Plugin-System** — jede `.py`-Datei in `plugins/` wird automatisch geladen; AION kann selbst neue erstellen
- **CLIO-Reflexion** — Konfidenz-Check und Gedanken-Protokoll nach jeder Nutzer-Nachricht

---

## Voraussetzungen

- Python 3.10+
- Windows (für `shell_exec`, `winget_install`)
- Google Gemini API-Key (empfohlen) und/oder OpenAI API-Key

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Konfiguration

Erstelle eine `.env`-Datei im Projektverzeichnis:

```env
GEMINI_API_KEY=AIza...           # empfohlen
OPENAI_API_KEY=sk-...            # optional
TELEGRAM_BOT_TOKEN=1234...:AAE...  # optional
TELEGRAM_CHAT_ID=123456789         # optional
AION_MODEL=gemini-2.5-flash        # optional, default: gpt-4.1
AION_PORT=7000                     # optional, default: 7000
```

Das aktive Modell wird in `config.json` gespeichert und beim nächsten Start wiederhergestellt.

---

## Starten / Stoppen

```bash
start.bat    # Startet Server + öffnet Browser (killt alte Instanzen automatisch)
stop.bat     # Stoppt alle AION-Prozesse sauber
restart.bat  # Stop + Start
status.bat   # Zeigt ob Server läuft
```

Oder manuell:
```bash
python aion_web.py   # Web-Server (Port 7000)
python aion.py       # CLI-Modus
```

---

## Web UI

Öffnet sich automatisch unter `http://localhost:7000`

- **Chat** (links): Eingabe und Antworten mit Token-Streaming
- **Gedanken** (rechts, Tab 1): AIons Reflexionen in Echtzeit — vollständig, mit Zeilenumbrüchen
- **Tools** (rechts, Tab 2): Tool-Aufrufe mit Ein-/Ausgabe — nur bei Klick aufgeklappt
- **Modell-Wechsel**: Dropdown oben rechts — wechselt sofort und persistiert in `config.json`

---

## Geplante Aufgaben (Scheduler)

AION kann Aufgaben zu festen Uhrzeiten selbstständig ausführen:

```
"Plane täglich um 06:00: Lese meine Emails, extrahiere Termine und trage sie in den Kalender ein."
"Plane werktags um 08:00: Schreibe mir eine kurze Tages-Zusammenfassung via Telegram."
"Plane jeden Montag um 09:00: Erstelle einen Wochenplan."
```

AION legt den Task mit `schedule_add` an und führt ihn zur geplanten Zeit aus.
Das Ergebnis wird automatisch per Telegram gesendet (wenn konfiguriert).

Verwaltung per Sprache oder direkt:
- `schedule_list` — alle Tasks anzeigen
- `schedule_remove` — Task löschen
- `schedule_toggle` — Task aktivieren/deaktivieren

---

## Telegram

1. Bot bei [@BotFather](https://t.me/BotFather) erstellen → Token
2. `TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID` in `.env` setzen
3. AION starten — Telegram-Polling startet automatisch

AION schreibt dir von sich aus, wenn:
- Ein Scheduler-Task abgeschlossen ist
- Du ihm sagst `"Schreib mir via Telegram wenn X fertig ist"`

---

## Plugin erstellen

Jede Datei in `plugins/<name>/<name>.py` muss eine `register(api)`-Funktion haben:

```python
def register(api):
    def mein_tool(input: dict) -> dict:
        return {"ok": True, "result": input.get("param")}

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

## Dateisystem

```
AION/
├── aion.py                      # Kernlogik: Memory, Tools, LLM-Loop, CLI
├── aion_web.py                  # Web-Server (FastAPI + SSE), Port 7000
├── plugin_loader.py             # Lädt alle Plugins aus plugins/
├── static/index.html            # Web UI (Vanilla JS)
├── plugins/
│   ├── scheduler/               # ★ Cron-Scheduler (schedule_add/list/remove/toggle)
│   ├── telegram_bot/            # Telegram bidirektional
│   ├── gemini_provider/         # Google Gemini + switch_model
│   ├── memory_plugin/           # Konversationshistorie (JSONL)
│   ├── clio_reflection/         # CLIO-Konfidenz-Check
│   ├── todo_tools/              # Aufgabenverwaltung
│   ├── smart_patch/             # Fuzzy-Code-Patching
│   ├── image_search/            # Bildersuche (Openverse + Bing)
│   ├── docx_tool/               # Word-Dokumente erstellen
│   └── heartbeat/               # Keep-Alive Timestamp
├── character.md                 # Persönlichkeit (selbst-aktualisierend)
├── AION_SELF.md                 # Selbst-Dokumentation für AION
├── aion_documentation.md        # Interne technische Dokumentation
├── aion_memory.json             # Persistentes Gedächtnis (max. 300 Einträge)
├── thoughts.md                  # Aufgezeichnete Gedanken
├── .env                         # API-Keys (nicht in Git)
├── config.json                  # Aktives Modell + Gesprächszähler
├── start.bat                    # Startet Server + Browser
├── stop.bat                     # Stoppt alle AION-Prozesse
├── restart.bat                  # Neustart
└── status.bat                   # Server-Status prüfen
```

---

## Verfügbare Modelle

| Provider | Modell | Empfehlung |
|---------|--------|-----------|
| Google Gemini | `gemini-2.5-pro` | ★ Beste Qualität |
| Google Gemini | `gemini-2.5-flash` | Schnell & günstig |
| Google Gemini | `gemini-2.0-flash` | Stabil |
| OpenAI | `gpt-4.1` | OpenAI Flagship |
| OpenAI | `gpt-4o` | Multimodal |
| OpenAI | `o3` | Reasoning |
| OpenAI | `o4-mini` | Schnell |

Wechsel per Web UI (Dropdown) oder Sprache: `"Wechsle zu gemini-2.5-pro"`

---

## Sicherheitshinweis

- `.env` ist in `.gitignore` — API-Keys niemals committen
- `shell_exec` führt beliebige Windows-Befehle aus — nur auf vertrauenswürdigen Systemen
- `self_modify_code` / `self_patch_code` — AION fragt vor Code-Änderungen um Bestätigung
- Scheduler-Tasks laufen mit vollen AION-Rechten — Tasks sorgfältig formulieren
