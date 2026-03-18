# AION — Interne Dokumentation
> Diese Datei wird von AION selbst gepflegt. Stand: aktuell.

---

## 1. Architektur-Überblick

```
Nutzer / Telegram / Scheduler
        ↓
   AionSession.turn() / .stream()
        ↓
   _build_system_prompt()  ←── character.md + Gedächtnis
        ↓
   LLM API (OpenAI oder Gemini via gemini_provider)
        ↓
   Tool-Calls → _dispatch() → Plugin-Funktionen
        ↓
   Ergebnis → nächste Iteration (max. 20×)
        ↓
   done-Event / Telegram-Nachricht
```

**Zwei Einstiegspunkte:**
- `AionSession.stream()` — SSE-Streaming für Web UI (token/tool_call/thought/done Events)
- `AionSession.turn()` — Blockierend, gibt fertigen Text zurück (für Telegram, Scheduler)

---

## 2. Bekannte Probleme & Status

| Problem | Status |
|---------|--------|
| Konversationshistorie überlebt Neustarts nicht | ✅ Behoben — `conversation_history.jsonl` wird persistent geladen |
| Modell-Auswahl nach Neustart weg | ✅ Behoben — in `config.json` persistiert |
| AION kündigt Aktionen an ohne sie auszuführen | ✅ Behoben — Completion-Check läuft jetzt auch bei _iter==0 |
| Doppelte Antwort-Bubbles im Web UI | ✅ Behoben — "KEIN ZWISCHENTEXT"-Regel + awaitingNewBubble-Logik |
| Gemini Tool-Cards öffnen immer erste | ✅ Behoben — globaler ID-Zähler in gemini_provider |
| Gedanken abgeschnitten im Web UI | ✅ Behoben — white-space:pre-wrap + keine Python-Truncation |
| Telegram 409 Conflict bei Neustart | ✅ Behoben — start.bat killt alte Instanzen |
| character.md wird nie befüllt | ✅ Behoben — exchange_count persistiert, Auto-Update um Humor/Eigenheiten erweitert |
| Heartbeat hat keine echte Cron-Funktion | ✅ Behoben — neues Scheduler-Plugin mit schedule_add/list/remove/toggle |

---

## 3. Kernabläufe

### 3.1 Tool-Loop (`aion.py → AionSession.stream()`)

```
for _iter in range(MAX_TOOL_ITERATIONS=20):
    LLM aufrufen (streaming)

    if tool_calls vorhanden:
        → Tools dispatchen
        → Ergebnisse in messages einfügen
        → nächste Iteration

    else (nur Text):
        → Completion-Check (LLM: FERTIG oder WEITER?)
        if WEITER:
            → [System]-Message einfügen → continue
        if FERTIG:
            → auto-reflect (bei _iter==0)
            → break
```

### 3.2 Completion-Check (verhindert vorzeitiges Stoppen)

Läuft nach JEDER Text-Antwort ohne Tool-Calls (auch bei iter==0).
Fragt das LLM: "War das die fertige Aufgabe oder gibt es noch Schritte?"
- FERTIG → break, Antwort an Nutzer
- WEITER: `<Grund>` → `[System] Bitte fahre fort: <Grund>` → nächste Iteration

### 3.3 Scheduler-Loop (`plugins/scheduler/scheduler.py`)

```
Thread läuft alle 10 Sekunden:
    now = datetime.now()
    für jeden Task in tasks.json:
        if Uhrzeit passt + Wochentag passt + heute noch nicht gelaufen:
            AionSession(channel="scheduler").turn(task["task"])
            → Ergebnis per Telegram senden
            → last_run setzen
```

### 3.4 Character-Update (`_auto_character_update`)

Läuft alle 5 Gespräche (exchange_count aus config.json, überlebt Neustarts).
LLM analysiert letzte 12 Nachrichten und schreibt Erkenntnisse in `character.md`:
- Nutzer-Fakten → section "nutzer"
- AION-Erkenntnisse → section "erkenntnisse"
- Humor-Entwicklung → section "humor"
- Eigenheiten → section "eigenheiten"

---

## 4. Plugin-Verzeichnis (aktuell)

| Plugin | Tools | Beschreibung |
|--------|-------|-------------|
| `gemini_provider` | `switch_model` | Google Gemini API + Modellwechsel |
| `telegram_bot` | `send_telegram_message` | Telegram bidirektional |
| `memory_plugin` | `memory_append_history`, `memory_read_history`, `memory_search_context` | Konversationshistorie JSONL |
| `clio_reflection` | `clio_check` | Konfidenz-Check vor jedem Turn |
| `todo_tools` | `todo_add`, `todo_list`, `todo_remove` | Aufgabenverwaltung |
| `smart_patch` | `smart_patch` | Fuzzy-Code-Patching mit difflib |
| `heartbeat` | `heartbeat_last` | Timestamp-Logging (Keep-Alive) |
| `scheduler` | `schedule_add`, `schedule_list`, `schedule_remove`, `schedule_toggle` | Cron-ähnlicher Task-Scheduler |
| `image_search` | `image_search` | Bildersuche (Openverse + Bing/Playwright-Fallback) |
| `docx_tool` | `create_docx` | Word-Dokumente erstellen |
| `pid_tool` | — | Prozess-ID Hilfstool |
| `restart_tool` | `self_restart` | Neustart-Plugin |

---

## 5. SSE-Event-Typen (Web UI)

| Event | Felder | Beschreibung |
|-------|--------|-------------|
| `token` | `content` | Einzelnes Text-Token (streaming) |
| `thought` | `text`, `trigger`, `call_id` | AION-Gedanke (reflect/clio/auto-reflect) |
| `tool_call` | `tool`, `args`, `call_id` | Tool wird aufgerufen |
| `tool_result` | `tool`, `result`, `ok`, `duration`, `call_id` | Tool-Ergebnis |
| `done` | `full_response`, `response_blocks` | Turn abgeschlossen |
| `error` | `message` | Fehler aufgetreten |

`response_blocks` = `[{type: "text", content: "..."}, {type: "image", url: "..."}]`

---

## 6. Wichtige Regeln (System-Prompt Highlights)

- **KEIN ZWISCHENTEXT**: Text schreiben UND danach Tool aufrufen = Bug → doppelte Bubbles
- **continue_work**: nach JEDEM Tool-Ergebnis wenn weitere Schritte folgen
- **Bilder**: NIEMALS `![text](url)` schreiben — immer `image_search` Tool nutzen
- **Code-Änderungen**: self_patch_code immer zuerst um Bestätigung fragen
- **self_restart**: ist jetzt Hot-Reload (load_plugins), kein sys.exit()

---

## 7. Datei-Referenz

| Datei | Beschreibung |
|-------|-------------|
| `aion.py` | Kernlogik: Memory, Tools, LLM-Loop, AionSession, CLI |
| `aion_web.py` | FastAPI Web-Server, SSE-Streaming, Port 7000 |
| `plugin_loader.py` | Lädt alle Plugins aus `plugins/` |
| `static/index.html` | Web UI (Vanilla JS, zwei Tabs: Gedanken / Tools) |
| `character.md` | AION-Persönlichkeit (selbst-aktualisierend alle 5 Gespräche) |
| `aion_memory.json` | Persistentes Gedächtnis (max. 300 Einträge, FIFO) |
| `conversation_history.jsonl` | Vollständige Konversationshistorie |
| `thoughts.md` | Aufgezeichnete Gedanken (reflect-Tool) |
| `config.json` | Aktives Modell + exchange_count (persistiert) |
| `.env` | API-Keys (niemals committen) |
| `plugins/scheduler/tasks.json` | Geplante Aufgaben (auto-generiert) |
