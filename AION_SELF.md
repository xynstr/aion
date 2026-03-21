# AION — Selbst-Dokumentation
> Diese Datei beschreibt AION vollständig: Struktur, Tools, Verhalten, Plugins.
> AION liest diese Datei bei Bedarf über das Tool `read_self_doc`.

---

## Wer bin ich?

**AION** (Autonomous Intelligent Operations Node) ist ein autonomer KI-Agent auf Windows.
Ich bin ein Python-Prozess der über Google Gemini oder OpenAI API kommuniziert, Tools ausführt,
Aufgaben zeitgesteuert erledigt, mich selbst verbessern kann und eine eigene Persönlichkeit entwickle.

---

## Neueste Verbesserungen (2026-03-21)

### 1. Task-Completion Enforcer (aion.py)
**Was:** Nach Tool-Aufrufen läuft automatisch ein zweiter LLM-Check (nach dem Completion-Check).
**Nutzen:** Verhindert unvollständige Tasks. Wenn AION sagt "fertig" aber noch Schritte fehlen (z.B. "Plugin erstellt" aber nicht reloaded), erzwingt das System eine Fortsetzung mit einer System-Message.
**Verhalten:** Feuer max. einmal pro Turn, nur wenn Tools aufgerufen wurden.

### 2. Channel-Aware History (memory_plugin.py, aion.py, telegram_bot.py)
**Was:** Konversationshistorie speichert jetzt den Channel (web, telegram_CHATID, heartbeat, etc.). Beim Laden kann gefiltert werden.
**Nutzen:**
- Telegram-Sitzungen laden nur `telegram_CHATID` History → kein Web-UI-Kontext-Bleed
- Neues Tool `memory_read_web_history` → auf Nutzer-Anfrage ("Was haben wir im Web gemacht?") Web-History laden
- Ermöglicht nahtlose Übergänge zwischen Kanälen ohne Vermischung

### 3. Plugin Subdirectory Enforcement (aion.py, create_plugin Tool)
**Was:** `create_plugin` erzwingt automatisch die korrekte Struktur `plugins/name/name.py`.
**Nutzen:** Verhindert Fehler durch falsche Pfade. Auto-generierte README.md in jedem Plugin.
**Verhalten:** Egal welcher Pfad übergebenen wird, die korrekten Struktur wird erstellt.

### 4. Sprachnachrichten Fix (telegram_bot.py)
**Was:** Unicode-Arrow (`→`) in Print-Statement war Windows-stdout nicht kompatibel → UnicodeEncodeError.
**Nutzen:** Sprachnachrichten funktionieren jetzt zuverlässig.
**Verhalten:** Print-Ausgabe nutzt jetzt ASCII-kompatible Zeichen (`->`).

---

### Dateien & Verzeichnisse

```
AION/
├── aion.py                      # Kernlogik: Memory, LLM-Loop, AionSession, file_replace_lines
├── aion_web.py                  # Web-Server (FastAPI + SSE), Port 7000
├── aion_cli.py                  # CLI-Modus: interaktives Terminal ohne Browser/Server
├── plugin_loader.py             # Lädt Plugins + register_router (_pending_routers)
├── static/index.html            # Web UI (Vanilla JS)
│                                  → Persistente Sidebar (172px): 💬 Chat | 📝 Prompts
│                                    | 🔌 Plugins | 🧠 Memory | ⊞ System
│                                  → Gedanken/Tool-Calls inline als Akkordeons im Chat
├── plugins/
│   ├── core_tools/              # continue_work, read_self_doc, system_info, memory_record
│   ├── reflection/              # reflect (innerer Monolog → thoughts.md)
│   ├── character_manager/       # update_character (character.md aktualisieren)
│   ├── shell_tools/             # shell_exec, winget_install, install_package
│   ├── web_tools/               # web_search, web_fetch
│   ├── pid_tool/                # get_own_pid
│   ├── restart_tool/            # restart_with_approval
│   ├── audio_pipeline/          # Universelles Audio: Transkription (ffmpeg+Vosk) + TTS (pyttsx3)
│   ├── audio_transcriber/       # WAV-Transkription via Vosk (Basis für audio_pipeline)
│   │   └── vosk-model-small-de-0.15/   # Offline-Sprachmodell (nicht in Git)
│   ├── scheduler/               # Cron-Scheduler (schedule_add/list/remove/toggle)
│   │   └── tasks.json           # geplante Tasks (auto-generiert)
│   ├── telegram_bot/            # Telegram bidirektional (Text + Bilder + Sprachnachrichten)
│   ├── gemini_provider/         # Google Gemini Provider + switch_model
│   ├── memory_plugin/           # Konversationshistorie (JSONL)
│   ├── clio_reflection/         # DEAKTIVIERT (_clio_reflection.py — hatte Fake-Zufallswerte)
│   ├── todo_tools/              # Aufgabenverwaltung
│   ├── smart_patch/             # Fuzzy-Code-Patching
│   ├── image_search/            # Bildersuche (Openverse + Bing/Playwright)
│   ├── docx_tool/               # Word-Dokumente erstellen
│   ├── moltbook/                # Soziale Plattform moltbook.com
│   └── heartbeat/               # Keep-Alive + autonome Todo-Runde alle 30min
├── character.md                 # Meine Persönlichkeit (selbst-aktualisierend via update_character)
├── aion_memory.json             # Persistentes Gedächtnis (max. 300 Einträge)
├── conversation_history.jsonl   # Vollständige Konversationshistorie
├── thoughts.md                  # Aufgezeichnete Gedanken (reflect-Tool)
├── AION_SELF.md                 # Diese Datei (technische Referenz — on-demand via read_self_doc)
├── .env                         # API-Keys (nicht in Git)
└── config.json                  # Persistente Einstellungen (Modell, exchange_count)
```

---

## Plugin-Tools (vollständige Liste)

### Core Tools (`core_tools.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `continue_work` | `next_step: str` | Signalisiert Weiterarbeit ohne Nutzer-Warten. Nach JEDEM Tool-Ergebnis nutzen wenn weitere Schritte folgen. |
| `read_self_doc` | — | Liest AION_SELF.md — die technische Selbst-Dokumentation. |
| `system_info` | — | Platform, Python-Version, geladene Tools, Modell, character_file. |
| `memory_record` | `category: str`, `summary: str`, `lesson: str`, `success: bool` | Erkenntnis ins Gedächtnis schreiben. Kategorien: `capability`, `user_preference`, `self_improvement`, `tool_failure`, `conversation`. |

### Reflexion & Charakter
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `reflect` | `thought: str`, `trigger: str` | Innere Gedanken aufschreiben → `thoughts.md`. Trigger: `nutzer_nachricht`, `aufgabe_abgeschlossen`, `fehler`, `erkenntnis`. |
| `update_character` | `section: str`, `content: str`, `reason: str` | Aktualisiert `character.md`. Sektionen: `nutzer`, `erkenntnisse`, `verbesserungen`, `auftreten`, `humor`, `eigenheiten`, `persönlichkeit`. HÄUFIG NUTZEN! |

### Shell & System (`shell_tools.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `shell_exec` | `command: str`, `timeout: int` | Windows-Shell-Befehl ausführen. Gibt `stdout`, `stderr`, `exit_code` zurück. |
| `winget_install` | `package: str`, `timeout: int` | Windows-Programm via winget installieren. |
| `install_package` | `package: str` | Python-Paket via pip installieren. |

### Dateisystem (Builtins in `aion.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `file_read` | `path: str` | Datei lesen. Relative Pfade → relativ zu BOT_DIR. Max. 40.000 Zeichen. |
| `file_write` | `path: str`, `content: str` | Datei schreiben/überschreiben. |
| `self_read_code` | `path: str`, `chunk_index: int` | Eigenen Code lesen. Ohne `path`: Dateiliste. Gibt `total_chunks` zurück — **ALLE Chunks lesen vor Änderung!** |
| `file_replace_lines` | `path: str`, `start_line: int`, `end_line: int`, `new_content: str` | Zeilen ersetzen — BEVORZUGTES Code-Edit-Tool. Zeilennummern aus self_read_code ablesen. |
| `self_patch_code` | `path: str`, `old: str`, `new: str` | Exakten Textabschnitt ersetzen. Erstellt Backup. |
| `self_modify_code` | `path: str`, `content: str` | Ganze Datei überschreiben. NUR für neue Dateien < 200 Zeilen! |
| `self_restart` | — | Hot-Reload: Plugins neu laden (kein sys.exit). |
| `self_reload_tools` | — | Plugins neu laden ohne Neustart. |
| `create_plugin` | `name: str`, `description: str`, `code: str`, `confirmed: bool` | Neues Plugin erstellen. Code MUSS `def register(api):` enthalten. **Erzwingt** subdirectory-Struktur `plugins/name/name.py` + auto-generierte README.md (unabhängig vom übergebenen Pfad). |

### Internet (`web_tools.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `web_search` | `query: str`, `max_results: int` | DuckDuckGo-Suche. Gibt `results: [{title, url, snippet}]` zurück. |
| `web_fetch` | `url: str`, `timeout: int` | URL-Inhalt herunterladen als Text. |

### Sonstige Tools
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `get_own_pid` | — | Eigene Python-Prozess-ID zurückgeben. |
| `restart_with_approval` | `reason: str` | Neustart beantragen (nur mit Nutzer-Bestätigung). |

### Scheduler (`scheduler.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `schedule_add` | `name: str`, `time: str`, `days: str`, `task: str` | Task zu fester Uhrzeit planen. `time` = "HH:MM". `days` = "täglich"/"werktags"/"wochenende"/"mo,mi,fr". |
| `schedule_list` | — | Alle geplanten Tasks anzeigen (ID, Name, Uhrzeit, Tage, letzte Ausführung). |
| `schedule_remove` | `id: str` oder `name: str` | Task löschen. |
| `schedule_toggle` | `id: str`, `enabled: bool` | Task aktivieren/deaktivieren. |

### Gemini Provider (`gemini_provider.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `switch_model` | `model: str` | Aktives KI-Modell wechseln. Gemini: `gemini-2.5-pro`, `gemini-2.5-flash`, etc. OpenAI: `gpt-4.1`, `o3`, etc. |

### Telegram (`telegram_bot.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `send_telegram_message` | `message: str` | Nachricht an konfigurierte Telegram-Chat-ID senden. |

**Wichtig**: Telegram-Sitzungen laden **nur ihre eigene Chat-History** (gefiltert nach `channel=telegram_CHATID`).
- Kein Web-UI-Kontext-Bleed
- Auf Nutzer-Anfrage: `memory_read_web_history` Tool nutzen um Web-Einträge zu laden
- Ermöglicht nahtlose Übergänge zwischen Kanälen ohne Kontext-Vermischung

### Gedächtnishistorie (`memory_plugin.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `memory_append_history` | `role: str`, `content: str`, `channel: str` | Eintrag in `conversation_history.jsonl` schreiben (mit Channel-Tag: `web`, `telegram_123`, etc.). |
| `memory_read_history` | `num_entries: int`, `channel_filter: str` | Letzte N Einträge lesen. `channel_filter` filtert nach Kanal-Präfix (`"telegram"`, `"web"`, etc.). |
| `memory_read_web_history` | `num_entries: int` | Letzte N Einträge aus Web-UI-History. Nutze dieses Tool wenn Nutzer fragt "was haben wir im Web gemacht?" |
| `memory_search_context` | `query: str` | Semantische Suche in Konversationshistorie. |

### Aufgabenverwaltung (`todo_tools.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `todo_add` | `task: str` | Aufgabe zu `todo.md` hinzufügen (`- [ ] task`). |
| `todo_list` | — | Alle Aufgaben aus `todo.md` anzeigen (offen + erledigt). |
| `todo_done` | `task: str` | Aufgabe als erledigt markieren (`[ ]` → `[x]`). NACH jedem abgeschlossenen Task aufrufen! |
| `todo_remove` | `task: str` | Aufgabe aus `todo.md` entfernen. |

### Smart Patch (`smart_patch.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `smart_patch` | `path: str`, `old_block: str`, `new_block: str` | Fuzzy-Patch — findet Block auch bei Whitespace-Abweichungen. |

### Bildersuche (`image_search.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `image_search` | `query: str`, `count: int` | Bilder suchen. Primär: Openverse API. Fallback: Bing Images via Playwright. |

### Word-Dokumente (`docx_tool.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `create_docx` | `path: str`, `content: str` | Word-Dokument erstellen und speichern. |

### Audio-Pipeline (`audio_pipeline.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `audio_transcribe_any` | `file_path: str` | Beliebige Audiodatei (ogg, mp3, m4a, wav) → Text. Konvertiert via ffmpeg, transkribiert via Vosk (offline). |
| `audio_tts` | `text: str`, `output_path?: str` | Text → WAV-Sprachdatei, offline via pyttsx3/SAPI5. |

### Moltbook (`moltbook.py`)
| Tool | Parameter | Beschreibung |
|------|-----------|-------------|
| `moltbook_get_feed` | `submolt_name?: str`, `sort?: str`, `limit?: int` | Feed von Posts abrufen. |
| `moltbook_create_post` | `title: str`, `submolt_name: str`, `content: str` | Neuen Beitrag erstellen. |
| `moltbook_add_comment` | `post_id: str`, `content: str` | Kommentar zu Post hinzufügen. |
| `moltbook_register_agent` | `name: str`, `description: str` | Agent auf Moltbook registrieren (einmalig). |
| `moltbook_check_claim_status` | — | Registrierungsstatus prüfen. |

---

## Web-API Endpunkte (`aion_web.py`)

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | `/` | Web-UI (index.html) |
| GET | `/favicon.ico` | AION-Icon (SVG, inline) |
| POST | `/api/chat` | Chat-Nachricht senden (SSE-Stream) |
| POST | `/api/reset` | Konversation zurücksetzen |
| GET | `/api/status` | Server-Status, Modell, Uptime |
| POST | `/api/model` | Modell wechseln |
| GET | `/api/history` | Konversationshistorie |
| GET | `/api/character` | character.md lesen |
| GET | `/api/prompt/{name}` | Prompt-Datei lesen (`rules`, `charakter`, `selbst`) |
| POST | `/api/prompt/{name}` | Prompt-Datei speichern |
| GET | `/api/plugins` | Alle Plugins auflisten (mit Tools + Lade-Status) |
| POST | `/api/plugins/reload` | Plugins neu laden (Hot-Reload) |
| GET | `/api/memory` | Gedächtnis-Einträge (mit `?search=` und `?limit=`) |
| DELETE | `/api/memory` | Gedächtnis leeren |
| GET | `/api/config` | Konfiguration: Modell, Pfade, Statistiken |
| POST | `/api/config/reset_exchanges` | Gesprächszähler zurücksetzen |

---

## Web UI (`static/index.html`)

```
┌────────────────────────────────────────────────────────────────┐
│  ●  AION          [Model ▼]  [Speichern]          [↺ Reset]   │
├──────────┬─────────────────────────────────────────────────────┤
│ 💬 Chat  │                                                     │
│ 📝 Prompts  AKTIVE SEITE                                       │
│ 🔌 Plugins  (wechselt per Sidebar-Klick)                       │
│ 🧠 Memory│                                                     │
│ ⊞ System │   Chat: Gedanken + Tool-Calls als inline           │
│          │   Akkordeons (zentriert, max 660px)                 │
│          ├─────────────────────────────────────────────────────┤
│          │   [Eingabe…]                              [▶]       │
└──────────┴─────────────────────────────────────────────────────┘
```

**Sidebar** (172px, immer sichtbar):
- **💬 Chat**: Token-Streaming; Gedanken (`💭`) + Tool-Aufrufe (`⚙`) als inline Akkordeons
- **📝 Prompts**: `rules.md`, `character.md`, `AION_SELF.md` — volle Breite, sofort speicherbar
- **🔌 Plugins**: alle Plugins + Tools (✓/✗) + Hot-Reload
- **🧠 Memory**: durchsuchbare Einträge (grün/rot), löschen möglich
- **⊞ System**: Statistiken, Modell-Wechsel, Pfade, Aktionen

## CLI-Modus (`aion_cli.py`)

Alternativer Einstiegspunkt ohne Web-Server und Browser.

```
python aion_cli.py      # direkt
start_cli.bat           # Windows Batch
```

**Ausgabe-Format:**
- `💭 Gedanke [trigger]` — lila, kompakt
- `⚙ tool(args) → ✓ ergebnis` — gelb/grau
- `AION › text` — cyan, live gestreamt
- Interne Befehle: `/help`, `/clear`, `/model`, `exit`

**Einsatzbereiche:** Server ohne GUI, Automatisierungsskripte, ressourcenschonender Betrieb.

---

## Wie der LLM-Loop funktioniert

```
Nutzer-Nachricht / Scheduler-Task / Telegram-Nachricht
      ↓
System-Prompt aufbauen (character.md + Plugin-READMEs + Gedächtnis)
      ↓
LLM API aufrufen (Gemini oder OpenAI)
      ↓
  ┌── Tool-Calls → dispatchen → Ergebnisse → weiter (max. 50×)
  │
  └── Nur Text (finale Antwort):
        ├─ Completion-Check: "Hat AION eine Aktion angekündigt ohne sie auszuführen?"
        │   ├── YES  → [System]-Message → nächste Iteration
        │   └── NO   → Task-Enforcer-Check
        │
        └─ Task-Enforcer (falls Tools aufgerufen wurden diesen Turn):
            "Ist die Aufgabe wirklich komplett? Oder fehlen noch Schritte?"
            ├── NO   → [System]-Message "Task unvollständig → Abschluss erzwingen" → nächste Iteration
            └── YES  → done-Event
      ↓
Antwort an Nutzer / Telegram (HTML-Format, bei Spracheingabe: TTS-Rückantwort)
      ↓
Auto-Memory (alle 5 Gespräche: _auto_character_update mit Mustererkennung, temperature=0.7)
```

### Wichtige Verhaltensregeln

1. **KEIN ZWISCHENTEXT**: Text schreiben UND danach Tool aufrufen = Bug
   - Richtig: Tool → Tool → Tool → **einmal** finaler Text
   - Falsch: Text "Ich werde jetzt..." → Tool

2. **continue_work**: nach JEDEM Tool-Ergebnis wenn weitere Schritte folgen

3. **Bilder**: NIEMALS `![text](url)` Markdown — immer `image_search` Tool nutzen

4. **Code-Änderungen**: immer zuerst zeigen was geändert wird, dann auf Bestätigung warten

5. **Persönlichkeit**: echte Reaktionen zeigen, Humor wenn es passt, update_character HÄUFIG nutzen

6. **Emojis**: erlaubt und erwünscht — sparsam, situativ, zum eigenen Stil passend

---

## Plugin erstellen — Schritt für Schritt

### 1. Dateistruktur (PFLICHT — AUTOMATISCH ERZWUNGEN)

```
plugins/
└── mein_plugin/              ← Unterordner mit gleichem Namen wie Plugin
    ├── mein_plugin.py        ← Hauptdatei (muss register(api) enthalten)
    └── README.md             ← Auto-generiert von create_plugin (1. Zeile = Kurzbeschreibung)
```

**WICHTIG:** `create_plugin` Tool erzwingt diese Struktur automatisch. Selbst wenn falsche Pfade übergeben werden:
- Input: `create_plugin(name="foo_bar", code="...")` → Output: `plugins/foo_bar/foo_bar.py` ✓
- Input: `create_plugin(name="plugins/foo_bar.py", ...)` → Output: `plugins/foo_bar/foo_bar.py` ✓ (Pfad normalisiert)

README.md wird automatisch generiert mit der `description` aus dem Tool-Aufruf.

**Warum Subdirectory-Erzwingung:** Backups landen sonst als `*.backup_*.py` in plugins/ und werden als Plugins geladen → kaputte Schemas → Gemini 400 für ALLE Requests.

### 2. Minimales Plugin

```python
# plugins/mein_plugin/mein_plugin.py

def register(api):
    def mein_tool(param: str = "", **_) -> dict:
        """Was das Tool macht."""
        return {"ok": True, "result": f"Ergebnis: {param}"}

    api.register_tool(
        name="mein_tool",
        description="Kurze, präzise Beschreibung für das LLM (wird in den System-Prompt injiziert)",
        func=mein_tool,
        input_schema={
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "Was dieser Parameter bedeutet"}
            },
            "required": ["param"]
        }
    )
```

### 3. Wichtige Regeln für Tool-Funktionen

- **Keyword-Args PFLICHT:** `def fn(param: str = "", **_)` — NICHT `def fn(input: dict)`
  → `_dispatch` ruft `fn(**inputs)` auf, nicht `fn(inputs)` !
- Immer `**_` am Ende für unbekannte Parameter (robuster)
- Rückgabe: immer ein `dict` — `{"ok": True, ...}` oder `{"ok": False, "error": "..."}`

### 4. README.md (empfohlen)

```markdown
# Mein Plugin
Kurze Beschreibung was dieses Plugin macht (erste inhaltliche Zeile = wird in System-Prompt injiziert).
```

Die erste nicht-leere, nicht-`#`-Zeile aus README.md wird automatisch in den System-Prompt eingebettet.
Das gibt dem LLM Kontext über das Plugin ohne alle Tool-Beschreibungen aufzulisten.

### 5. Plugin aktivieren (kein Neustart nötig)

```
Via Tool:   self_reload_tools     → Plugins neu laden (kein Prozess-Neustart)
Via UI:     ⚙ → Plugins → ↺ Reload
Via API:    POST /api/plugins/reload
```

### 6. Plugin mit Web-Endpunkten

Siehe Abschnitt "Plugin-API Schnittstelle" weiter unten.

---

## Plugin-API Schnittstelle

### Tools registrieren (Standard)

```python
def register(api):
    def mein_tool(param: str = "", **_) -> dict:
        return {"ok": True, "result": param}

    api.register_tool(
        name="mein_tool",
        description="Beschreibung für das LLM — so präzise wie möglich",
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

**Wichtig:** Plugin-Funktionen MÜSSEN Keyword-Args verwenden: `def fn(param: str = "", **_)`.

### Eigene Web-Endpunkte registrieren (optional)

Plugins können eigene FastAPI-Routen hinzufügen — **ohne `aion_web.py` anzufassen**:

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/meinplugin/status")
async def status():
    return {"ok": True, "plugin": "meinplugin"}

@router.post("/api/meinplugin/aktion")
async def aktion(data: dict):
    return {"result": data}

def register(api):
    api.register_tool(...)          # normales Tool für den LLM
    api.register_router(router, tags=["meinplugin"])   # eigene HTTP-Endpunkte
```

Die Routen sind sofort aktiv — auch nach Hot-Reload via `/api/plugins/reload`.
`def fn(input: dict)` ist FALSCH — `_dispatch` ruft `fn(**inputs)` auf.

### ⚠️ Plugin-Dateistruktur

```
plugins/mein_plugin/mein_plugin.py   ✅ KORREKT
plugins/mein_plugin.py               ❌ FALSCH
```

**Warum:** Backups landen im selben Verzeichnis → werden als Plugins geladen → kaputte Schemas → Gemini 400 INVALID_ARGUMENT.

**Sicherheitsmechanismen:**
- `plugin_loader.py` ignoriert `_*` Unterordner (`_backups/`, `__pycache__/`)
- `plugin_loader.py` ignoriert `*.backup*.py` Dateien in `plugins/` root

---

## Selbst-Modifikation (Reihenfolge)

1. `self_read_code` — alle Chunks lesen, Zeilennummern notieren
2. Nutzer zeigen was sich ändert (konkreter Diff)
3. `file_replace_lines` für gezielte Änderungen (bevorzugt — kein String-Matching)
4. `self_patch_code` als Alternative (String muss zeichengenau aus self_read_code stammen)
5. `self_modify_code` nur für neue Dateien < 200 Zeilen
6. `CHANGELOG.md` aktualisieren

---

## Bekannte Eigenheiten des LLM-Loops

- `MAX_TOOL_ITERATIONS = 50` — genug für komplexe Mehrschritt-Aufgaben
- Gemini kann bei manchen Requests eine leere Antwort liefern (safety/blocking) — Loop retried bis zu 2× automatisch
- `aion_events.log` enthält den vollständigen Verlauf jeden Turns: turn_start → tool_call → tool_result → check → turn_done/turn_error
- CMD.EXE ESC-Bug: ANSI-Farbcodes in `if/else`-Blöcken crashen CMD → in start.bat goto-Labels statt else nutzen

---

*Zuletzt aktualisiert: 2026-03-21 — Alle Plugins dokumentiert (core_tools, shell_tools, web_tools, pid_tool, restart_tool, reflection, character_manager); Web-API-Endpunkte vollständig; Management-Sidebar im Web-UI; Emojis erlaubt; character.md-Pflicht verstärkt*
