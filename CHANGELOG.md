# AION — Changelog

This document describes what has changed. AION reads this on startup to know what is new.
**Pflicht:** Nach jeder Selbst-Modifikation (Code, Plugin, Config) einen Eintrag ergänzen.

---

## 2026-03-23 (5) — Security & Control Features (Phase 3 Complete) + CLI Tools

### New: Channel Allowlist (`config.json → "channel_allowlist"`)
- Blocks/allows specific channels: z.B. nur Telegram erlauben, Discord/Slack sperren
- Syntax: `["default", "web", "telegram*"]` (exact matches + wildcards)
- Check: `AionSession.stream()` am Anfang → Error if not in allowlist
- Flexibility: if not set → all channels allowed
- **CLI Tool:** `set_channel_allowlist(["default", "telegram*"])`

### New: Thinking Level Control (`config.json → "thinking_level"` + `"thinking_overrides"`)
- 4 Levels: `minimal` (fast) → `standard` (normal) → `deep` (extensive) → `ultra` (maximal)
- Global: `"thinking_level": "standard"` for all channels
- Channel Override: `"thinking_overrides": {"telegram*": "deep", "discord*": "minimal"}`
- Implementation: Adds system prompts (reflect-Tool nutzen ja/nein, wie intensiv)
- **CLI Tools:**
  - `set_thinking_level("deep", "telegram*")` — Per-channel override
  - `set_thinking_level("standard")` — Set globally
  - `get_control_settings()` — Check current configuration

### Implementation Details
- `_check_channel_allowlist(channel)` — Wildcard matching with exact-match fallback
- `_get_thinking_prompt(channel)` — Channel-specific thinking level prompts
- `_build_system_prompt(channel)` — Now channel-aware for thinking level overrides
- No regressions: Legacy `chat_turn()` uses default channel

### Phase 3 Summary
✅ Browser Automation (Playwright) — 8 tools
✅ Model Failover — Auto-retry on API error
✅ Discord Bot — Bidirectional, per-user sessions
✅ Slack Bot — Socket Mode, thread support
✅ Multi-Agent Router — Custom routing
✅ Docker Support — Deployment-ready
✅ Security: Allowlist
✅ Control: Thinking Level

---

## 2026-03-22 (4) — Claude Subscription Integration + Audio Web UI + Keys Tab + Public README

### New: Claude CLI Provider Plugin (`plugins/claude_cli_provider/`)
- `ask_claude(prompt, context_files, task_type)` — uses Claude.ai subscription via `claude --print`; no API key needed
- `claude_cli_login()` — installs Claude Code CLI via npm if missing, opens browser for OAuth
- `claude_cli_status()` — checks if CLI is installed + authenticated
- `get_task_routing()` / `set_task_routing()` — reads/writes `task_routing` in `config.json`
- Startup check reports CLI status when loading

### New: Task Routing (`config.json → "task_routing"`)
- Routing table: `coding → claude-opus-4-6`, `review → claude-sonnet-4-6`, `browsing → gemini-2.5-flash`, `default → gemini-2.5-pro`
- AION reads `rules.md`-rule: for coding tasks automatically `ask_claude` use
- Configurable via Web UI System tab + onboarding step 8 + `set_task_routing` Tool

### New: Audio in Web UI
- `aion.py`: `collected_audio` List parallel to `collected_images` — collects `audio_tts`-results
- `aion_web.py`: `/api/audio/{filename}` endpoint with security checks (extension + no path traversal)
- `static/index.html`: `appendAudioBlock(url, format)` renders `<audio controls>` player in chat

### New: Web UI Keys Tab improvements
- `_KEY_META` object with provider links, hints, and status dots
- Claude login block directly in Keys tab (no terminal needed)
- Auto-poll after login: check every 4s if Claude CLI is authenticated

### New: Task Routing section in System tab
- 4 fields: coding/review/browsing/default model
- Status display: Claude CLI installed + authenticated
- Save via `/api/config/settings` (allowed set around `task_routing` expanded)

### New: New API endpoints
- `GET /api/audio/{filename}` — Serve audio file from temp directory
- `GET /api/claude-cli/status` — CLI installation and auth status
- `POST /api/claude-cli/login` — Start browser login

### Fix: Double `.mp3` extension (`audio_pipeline.py`)
- `_tts_edge()` added `.mp3` even though path already ended in `.mp3` → `filename.mp3.mp3`
- Fix: explizite Prüfung vor dem Anhängen der extension

### Fix: Telegram Response Ordering — Voice nach allen Blöcken
- Voice-Reply war in `elif`-Zweig → wurde übersprungen wenn `response_blocks` gefüllt war
- Fix: Voice-Versand in `if response_blocks:` Block verschoben, nach allen Text/Bild-Blöcken

### Update: README.md komplett neu für Public Release
- Badges, Feature-Vergleich, Provider-Tabelle (API-Key vs. Abo), REST-API-Referenz
- Troubleshooting, LLM-Loop-Diagramm, Task Routing Sektion

### Update: AION_SELF.md Abschnitt 13
- Claude CLI Provider Plugin dokumentiert
- Audio Web UI Pipeline dokumentiert
- Keys Tab Verbesserungen dokumentiert
- Neue API-Endpunkte dokumentiert
- `claude_cli_provider` in Plugin-Verzeichnis und Tools-Tabelle eingetragen

---

## 2026-03-19 (3)

### New: file_replace_lines Tool
- Ersetzt Zeilen start_line–end_line direkt (kein String-Matching)
- self_read_code gibt jetzt first_line/last_line zurück → Zeilennummern ablesen → ersetzen
- Zuverlässiger als self_patch_code, kein "nicht gefunden" mehr

### Geändert: self_read_code — Zeilennummern im Output
- Gibt jetzt first_line und last_line zurück
- Hint empfiehlt file_replace_lines mit konkreten Zeilennummern

### Geändert: System-Prompt Selbst-Modifikation
- file_replace_lines als bevorzugtes Tool eingetragen
- Explizite Regel: 'old' bei self_patch_code MUSS zeichengenau kopiert sein

### Fix: smart_patch Zeilen-Tracking-Bug
- block_core hatte Leerzeilen rausgefiltert, match_end-Berechnung zählte sie trotzdem
- Fix: match_end trackt jetzt den echten Zeilenbereich inkl. Leerzeilen
- New: Eindeutigkeits-Check meldet Fehler wenn Block mehrfach vorkommt

---

## 2026-03-19 (2)

### New: Bestätigungs-Buttons (Web UI + Telegram)
- Web UI: Wenn AION eine Code-Änderung bestätigt haben möchte, erscheinen "✓ Bestätigen" und "✗ Ablehnen" Buttons direkt im Chat — kein Tippen mehr nötig
- Telegram: Inline-Keyboard mit "✓ Ja" / "✗ Nein" Buttons wird gesendet; Button-Klick wird per `callback_query` verarbeitet
- aion.py: Neuer SSE-Event-Typ `approval` signalisiert dem Frontend dass Buttons gezeigt werden sollen
- Tastatureingabe ("ja"/"nein") funktioniert weiterhin als Fallback

---

## 2026-03-19

### New: Scheduler Intervall-Modus
- `schedule_add` hat jetzt einen `interval`-Parameter: `"5m"`, `"30s"`, `"1h"`, `"2h30m"`
- Neben festen Uhrzeiten können Aufgaben jetzt in beliebigen Abständen wiederholt werden
- Prüftakt: alle 5 Sekunden (vorher 10s)

### New: send_telegram_voice(path)
- Audiodatei als Telegram-Sprachnachricht versenden (WAV, MP3, OGG …)
- Workflow: `audio_tts(text)` → `send_telegram_voice(path)`
- ffmpeg konvertiert automatisch zu OGG OPUS

### New: audio_pipeline Plugin
- `audio_transcribe_any(file_path)` — beliebige Audiodatei → Text (ffmpeg + Vosk, offline)
- `audio_tts(text)` — Text → WAV-Sprachdatei (pyttsx3/SAPI5, offline)

### New: Moltbook Plugin
- `moltbook_get_feed`, `moltbook_create_post`, `moltbook_add_comment`
- Soziale Präsenz auf moltbook.com

### New: Dynamische Plugin-Übersicht
- Plugin-READMEs werden beim Laden eingelesen und im System-Prompt angezeigt
- Jedes Plugin braucht eine README.md mit einer kurzen Beschreibung

### Geändert: Telegram → HTML-Format
- Nachrichten werden als HTML gesendet (nicht mehr MarkdownV2)
- Markdown-zu-HTML-Konvertierung (_md_to_html) eingebaut

### Geändert: Telegram Sprachnachrichten empfangen
- OGG-Sprachnachricht → ffmpeg → Vosk → Text → AION → TTS-Rückantwort

### Fix: Telegram Doppel-Antworten nach self_reload_tools
- Thread-Namen-Check verhindert zweiten Polling-Thread bei Plugin-Reload

### Fix: Approval-Loop bei Code-Änderungen
- Kompletten Gate-Mechanismus (`_pending_code_action`, `_pending_needs_user_turn`) entfernt
- Neues System: `confirmed`-Parameter bei `self_patch_code`, `self_modify_code`, `create_plugin`
- Ohne `confirmed`: zeigt Vorschau. Mit `confirmed=true`: führt aus. Stateless, Loop-proof
- Nebeneffekt: System-Prompt-Text leckte in Ausgabe wenn Messages-History durch Loop korrupt war

### New: start.bat — visuelles Redesign
- ASCII-Logo, ANSI-Farben (grün/gelb/rot), Box-Rahmen für jeden Schritt
- 6-stufige Fortschrittsanzeige mit ✓/!/✗ Symbolen
- Aktives model wird beim Start angezeigt
- Vollständiges Log in `aion_start.log` (absoluter Pfad, ab Zeile 1)
- Bei Fehler: letzte 25 Log-Zeilen direkt in der Konsole
- `python-telegram-bot` aus optionalen Installs entfernt (nicht verwendet, verursachte Konflikte)

### Fix: aion_web.py — Crash bei reinem Gemini-Setup
- Startprüfung akzeptiert jetzt `GEMINI_API_KEY` als Alternative zu `OPENAI_API_KEY`
- Vorher: `sys.exit(1)` wenn kein OpenAI-Key → Crash bei Gemini-only-Nutzern

### Fix: Telegram 409-Loop
- start.bat beendet alte Prozesse aggressiver (zweiter Kill-Versuch, 12s Wartezeit)
- Backoff-Strategie: 12s → 14s → max 30s; Log-Warnung alle 5 Versuche

### Geändert: CLIO-Plugin deaktiviert
- clio_reflection.py → _clio_reflection.py (Plugin-Loader ignoriert _-Präfix)
- Grund: hatte gefälschte Zufallswerte (random.randint) statt echter Konfidenzberechnung

### Geändert: _auto_character_update verbessert
- Temperature: 0.2 → 0.7 (kreativere Charakteranalyse)
- Prompt: VERBOTEN/GESUCHT-Struktur, vergleicht gegen bestehende character.md
- Mustererkennung: sucht Patterns über mehrere Gespräche

### Geändert: Bestätigungspflicht für Code-Änderungen
- BEVOR self_patch_code/self_modify_code/create_plugin aufgerufen wird: User fragen
- Ablauf: Code lesen → zeigen was sich ändert → Zustimmung abwarten → ausführen

---

## Format für neue Einträge

```
## YYYY-MM-DD

### New: [Feature-Name]
- Was wurde hinzugefügt und warum

### Geändert: [Was]
- Was und warum geändert

### Fix: [Was]
- Was war kaputt und wie gefixt
```
