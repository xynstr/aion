# AION — Autonomous Intelligent Operations Node

Ein autonomer KI-Agent für Windows. Läuft als Python-Prozess, kommuniziert über Google Gemini oder OpenAI API, führt Tools aus, lernt und kann sich selbst modifizieren.

---

## Features

- **Autonomes Arbeiten** — bis zu 50 Tool-Iterationen ohne Nutzer-Warten, mit automatischem Completion-Check
- **Geplante Aufgaben** — Scheduler mit Uhrzeiten (`06:00`) und Intervallen (`alle 5m`) — läuft vollständig autonom
- **Selbst-Modifikation** — liest, patcht und überschreibt eigenen Code; erstellt neue Plugins
- **Web UI** — Live-Stream von Antworten, Gedanken und Tool-Aufrufen; persistente Sidebar-Navigation (Chat / Prompts / Plugins / Memory / System)
- **CLI-Modus** — vollständig ohne Browser/Server: `start_cli.bat` oder `python aion_cli.py`; farbige Terminal-Ausgabe mit Tool-/Gedanken-Anzeige
- **Telegram** — bidirektional: Text, Bilder und Sprachnachrichten (OGG → Vosk-Transkription, TTS-Rückantwort)
- **Gedächtnis** — persistentes JSON-Gedächtnis + Konversationshistorie (JSONL)
- **Persönlichkeit** — `character.md` entwickelt sich durch Gespräche; alle 5 Gespräche LLM-Analyse mit Mustererkennung
- **Multi-Provider** — Google Gemini (2.5-pro, 2.5-flash …) und OpenAI (GPT-4.1, o3 …) wechselbar
- **Plugin-System** — `plugins/<name>/<name>.py` wird automatisch geladen; READMEs werden als Plugin-Übersicht injiziert
- **Audio-Pipeline** — beliebiges Audioformat → Transkription (ffmpeg + Vosk, offline) + TTS (pyttsx3/SAPI5, offline)
- **Moltbook** — soziale Präsenz: Feed lesen, Posts erstellen, kommentieren

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
start.bat        # Startet Web-Server + öffnet Browser (killt alte Instanzen)
start_cli.bat    # Startet interaktiven CLI-Modus (kein Browser nötig)
stop.bat         # Stoppt alle AION-Prozesse sauber
restart.bat      # Stop + Start
status.bat       # Zeigt ob Server läuft
```

Oder manuell:
```bash
python aion_web.py   # Web-Server (Port 7000)
python aion_cli.py   # CLI-Modus (interaktives Terminal)
```

---

## Web UI

Öffnet sich automatisch unter `http://localhost:7000`

```
┌────────────────────────────────────────────────────────────────┐
│  ●  AION          [Model ▼]  [Speichern]          [↺ Reset]   │
├──────────┬─────────────────────────────────────────────────────┤
│          │                                                     │
│ 💬 Chat  │   AKTIVE SEITE                                      │
│ 📝 Prompts   (wechselt je nach Sidebar-Auswahl)               │
│ 🔌 Plugins                                                     │
│ 🧠 Memory│   Chat: Token-Streaming, Gedanken + Tool-Calls      │
│ ⊞ System │         als inline Akkordeons (zentriert)           │
│          │                                                     │
│          ├─────────────────────────────────────────────────────┤
│          │   [Eingabe…]                              [▶]       │
└──────────┴─────────────────────────────────────────────────────┘
```

**Sidebar** (172px, immer sichtbar — kein Toggle):
- **💬 Chat** — Haupt-Chat; Gedanken + Tool-Aufrufe inline als aufklappbare Akkordeons
- **📝 Prompts** — `rules.md`, `character.md`, `AION_SELF.md` direkt im Browser bearbeiten (volle Breite)
- **🔌 Plugins** — alle Plugins mit Tools + Status (✓/✗) + Reload
- **🧠 Memory** — Gedächtnis durchsuchen, farbkodiert (grün/rot), löschen
- **⊞ System** — Statistiken, Modell wechseln, Pfade, Aktionen

## CLI-Modus

```
> start_cli.bat

  ╔══════════════════════════════════════╗
  ║  AION  —  CLI-Modus                  ║
  ╚══════════════════════════════════════╝

  AION wird initialisiert… ✓
  Modell: gemini-2.5-flash  |  Tools: 32

Du  › liste die dateien im projektverzeichnis auf
  ⚙  shell_exec({'command': 'dir /b'})  → ✓ aion.py aion_web.py aion_cli.py ...
AION › Hier sind die Dateien im Verzeichnis: ...

Du  › exit
  Sitzung beendet. Tschüss! 👋
```

- Gedanken erscheinen als `💭 …` in Lila
- Tool-Aufrufe als `⚙ tool(args) → ✓/✗ ergebnis` in Gelb/Grau
- Antworten als `AION › …` live gestreamt in Cyan
- Interne Befehle: `/help`, `/clear`, `/model`

---

## Geplante Aufgaben (Scheduler)

AION kann Aufgaben zu festen Uhrzeiten **oder in Intervallen** selbstständig ausführen:

```
"Plane täglich um 06:00: Lese meine Emails, extrahiere Termine und trage sie in den Kalender ein."
"Plane werktags um 08:00: Schreibe mir eine kurze Tages-Zusammenfassung via Telegram."
"Schreibe mir alle 5 Minuten eine Telegram-Nachricht mit dem aktuellen Status."
"Erinnere mich jede Stunde an meine Wasserration."
```

**Intervall-Syntax:** `"5m"`, `"30s"`, `"1h"`, `"2h30m"`, `"alle 10 Minuten"`

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
    def mein_tool(param: str = "", **_) -> dict:
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

**Wichtig:** `def fn(param: str = "", **_)` — keine `input: dict` Parameter!

### Plugin mit eigenen Web-Endpunkten

Plugins können auch eigene HTTP-Routen bereitstellen — ohne `aion_web.py` anzufassen:

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/meinplugin/status")
async def status():
    return {"ok": True}

def register(api):
    api.register_tool(...)                              # LLM-Tool wie gehabt
    api.register_router(router, tags=["meinplugin"])   # eigene HTTP-Routen
```

Neue Plugins werden sofort geladen — kein Neustart nötig (außer bei Änderungen an `aion.py`).
AION kann auch zur Laufzeit Plugins via `create_plugin` Tool erstellen.

---

## Web-API

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | `/api/status` | Server-Status, Modell, Uptime |
| POST | `/api/chat` | Chat-Nachricht senden (SSE-Stream) |
| POST | `/api/model` | Modell wechseln |
| GET | `/api/plugins` | Alle Plugins mit Tools + Lade-Status |
| POST | `/api/plugins/reload` | Plugins Hot-Reload |
| GET | `/api/memory` | Gedächtnis-Einträge (`?search=`, `?limit=`) |
| DELETE | `/api/memory` | Gedächtnis leeren |
| GET | `/api/config` | Konfiguration + Statistiken |
| GET | `/api/prompt/{name}` | Prompt lesen (`rules`, `charakter`, `selbst`) |
| POST | `/api/prompt/{name}` | Prompt speichern |

---

## Dateisystem

```
AION/
├── aion.py                      # Kernlogik: Memory, Tools, LLM-Loop, AionSession
├── aion_web.py                  # Web-Server (FastAPI + SSE), Port 7000
├── aion_cli.py                  # CLI-Modus: interaktives Terminal ohne Browser
├── plugin_loader.py             # Lädt Plugins + register_router Support
├── static/index.html            # Web UI (Vanilla JS, persistente Sidebar)
├── plugins/
│   ├── core_tools/              # continue_work, read_self_doc, system_info, memory_record
│   ├── reflection/              # reflect (innerer Monolog → thoughts.md)
│   ├── character_manager/       # update_character (character.md aktualisieren)
│   ├── shell_tools/             # shell_exec, winget_install, install_package
│   ├── web_tools/               # web_search, web_fetch
│   ├── pid_tool/                # get_own_pid
│   ├── restart_tool/            # restart_with_approval
│   ├── audio_pipeline/          # Beliebige Audiodatei → Text (ffmpeg+Vosk) + TTS (pyttsx3)
│   ├── audio_transcriber/       # WAV → Text via Vosk (Basis-Transkription)
│   ├── scheduler/               # Cron-Scheduler (schedule_add/list/remove/toggle)
│   ├── moltbook/                # Soziale Plattform moltbook.com (Feed, Posts, Kommentare)
│   ├── telegram_bot/            # Telegram: Text + Bilder + Sprachnachrichten
│   ├── gemini_provider/         # Google Gemini + switch_model
│   ├── memory_plugin/           # Konversationshistorie (JSONL)
│   ├── todo_tools/              # Aufgabenverwaltung
│   ├── smart_patch/             # Fuzzy-Code-Patching
│   ├── image_search/            # Bildersuche (Openverse + Bing)
│   ├── docx_tool/               # Word-Dokumente erstellen
│   └── heartbeat/               # Keep-Alive + autonome Todo-Bearbeitung (alle 30min)
├── character.md                 # Persönlichkeit (selbst-aktualisierend via update_character)
├── AION_SELF.md                 # Technische Selbst-Dokumentation für AION
├── aion_memory.json             # Persistentes Gedächtnis (max. 300 Einträge)
├── thoughts.md                  # Aufgezeichnete Gedanken
├── .env                         # API-Keys (nicht in Git)
├── config.json                  # Aktives Modell + Gesprächszähler
├── start.bat                    # Startet Web-Server + Browser
├── start_cli.bat                # Startet CLI-Modus (kein Browser)
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

Wechsel per Web UI (Dropdown oder Sidebar → System) oder Sprache: `"Wechsle zu gemini-2.5-pro"`

---

## Sicherheitshinweis

- `.env` ist in `.gitignore` — API-Keys niemals committen
- `shell_exec` führt beliebige Windows-Befehle aus — nur auf vertrauenswürdigen Systemen
- `self_modify_code` / `self_patch_code` — AION fragt vor Code-Änderungen um Bestätigung
- Scheduler-Tasks laufen mit vollen AION-Rechten — Tasks sorgfältig formulieren
