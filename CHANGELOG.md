# AION — Changelog

Hier steht was sich geändert hat. AION liest dieses Dokument beim Start und weiß so was neu ist.
**Pflicht:** Nach jeder Selbst-Modifikation (Code, Plugin, Config) einen Eintrag ergänzen.

---

## 2026-03-23 (5) — Security & Control Features (Phase 3 Complete)

### Neu: Channel Allowlist (`config.json → "channel_allowlist"`)
- Sperrt/erlaubt bestimmte Kanäle: z.B. nur Telegram erlauben, Discord/Slack sperren
- Syntax: `["default", "web", "telegram*"]` (exakte Matches + Wildcards)
- Prüfung: `AionSession.stream()` am Anfang → Fehler wenn nicht in Allowlist
- Flexibilität: Wenn nicht gesetzt → alle Kanäle erlaubt

### Neu: Thinking Level Control (`config.json → "thinking_level"` + `"thinking_overrides"`)
- 4 Level: `minimal` (schnell) → `standard` (normal) → `deep` (ausgiebig) → `ultra` (maximal)
- Global: `"thinking_level": "standard"` für alle Kanäle
- Channel-Override: `"thinking_overrides": {"telegram*": "deep", "discord*": "minimal"}`
- Implementierung: Fügt System-Prompts hinzu (reflect-Tool nutzen ja/nein, wie intensiv)

### Implementation Details
- `_check_channel_allowlist(channel)` — Wildcard-Matching mit Exact-Match Fallback
- `_get_thinking_prompt(channel)` — Channel-spezifische Thinking-Level Prompts
- `_build_system_prompt(channel)` — Jetzt Channel-aware für Thinking-Level Overrides
- Keine Regressions: Legacy `chat_turn()` nutzt Default-Channel

### Phase 3 Summary
✅ Browser Automation (Playwright) — 8 Tools
✅ Model Failover — Auto-Retry bei API-Fehler
✅ Discord Bot — Bidirektional, per-User Sessions
✅ Slack Bot — Socket Mode, Thread-Support
✅ Multi-Agent Router — Custom Routing
✅ Docker Support — Deployment-ready
✅ Security: Allowlist
✅ Control: Thinking Level

---

## 2026-03-22 (4) — Claude Abo-Integration + Audio Web UI + Keys Tab + Public README

### Neu: Claude CLI Provider Plugin (`plugins/claude_cli_provider/`)
- `ask_claude(prompt, context_files, task_type)` — nutzt Claude.ai-Abo via `claude --print`; kein API-Key nötig
- `claude_cli_login()` — installiert Claude Code CLI via npm falls fehlt, öffnet Browser für OAuth
- `claude_cli_status()` — prüft ob CLI installiert + angemeldet
- `get_task_routing()` / `set_task_routing()` — liest/schreibt `task_routing` in `config.json`
- Startup-Check meldet CLI-Status beim Laden

### Neu: Task Routing (`config.json → "task_routing"`)
- Routing-Tabelle: `coding → claude-opus-4-6`, `review → claude-sonnet-4-6`, `browsing → gemini-2.5-flash`, `default → gemini-2.5-pro`
- AION liest `rules.md`-Regel: für Code-Aufgaben automatisch `ask_claude` verwenden
- Konfigurierbar via Web UI System-Tab + onboarding Step 8 + `set_task_routing` Tool

### Neu: Audio im Web UI
- `aion.py`: `collected_audio` Liste parallel zu `collected_images` — sammelt `audio_tts`-Ergebnisse
- `aion_web.py`: `/api/audio/{filename}` Endpunkt mit Sicherheitsprüfungen (Extension + kein Path-Traversal)
- `static/index.html`: `appendAudioBlock(url, format)` rendert `<audio controls>` Player im Chat

### Neu: Web UI Keys-Tab Verbesserungen
- `_KEY_META` Objekt mit Provider-Links, Hinweisen und Status-Dots
- Claude-Login-Block direkt im Keys-Tab (kein Terminal nötig)
- Auto-Poll nach Login: alle 4s prüfen ob claude CLI authentifiziert

### Neu: Task Routing Sektion im System-Tab
- 4 Felder: coding/review/browsing/default Modell
- Status-Anzeige: Claude CLI installiert + angemeldet
- Speichern via `/api/config/settings` (allowed-Set um `task_routing` erweitert)

### Neu: Neue API Endpunkte
- `GET /api/audio/{filename}` — Audio-Datei aus Temp-Verzeichnis servieren
- `GET /api/claude-cli/status` — CLI-Installations- und Auth-Status
- `POST /api/claude-cli/login` — Browser-Login starten

### Fix: Double `.mp3` Extension (`audio_pipeline.py`)
- `_tts_edge()` fügte `.mp3` an, obwohl Pfad bereits auf `.mp3` endete → `filename.mp3.mp3`
- Fix: explizite Prüfung vor dem Anhängen der Extension

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

### Neu: file_replace_lines Tool
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
- Neu: Eindeutigkeits-Check meldet Fehler wenn Block mehrfach vorkommt

---

## 2026-03-19 (2)

### Neu: Bestätigungs-Buttons (Web UI + Telegram)
- Web UI: Wenn AION eine Code-Änderung bestätigt haben möchte, erscheinen "✓ Bestätigen" und "✗ Ablehnen" Buttons direkt im Chat — kein Tippen mehr nötig
- Telegram: Inline-Keyboard mit "✓ Ja" / "✗ Nein" Buttons wird gesendet; Button-Klick wird per `callback_query` verarbeitet
- aion.py: Neuer SSE-Event-Typ `approval` signalisiert dem Frontend dass Buttons gezeigt werden sollen
- Tastatureingabe ("ja"/"nein") funktioniert weiterhin als Fallback

---

## 2026-03-19

### Neu: Scheduler Intervall-Modus
- `schedule_add` hat jetzt einen `interval`-Parameter: `"5m"`, `"30s"`, `"1h"`, `"2h30m"`
- Neben festen Uhrzeiten können Aufgaben jetzt in beliebigen Abständen wiederholt werden
- Prüftakt: alle 5 Sekunden (vorher 10s)

### Neu: send_telegram_voice(path)
- Audiodatei als Telegram-Sprachnachricht versenden (WAV, MP3, OGG …)
- Workflow: `audio_tts(text)` → `send_telegram_voice(path)`
- ffmpeg konvertiert automatisch zu OGG OPUS

### Neu: audio_pipeline Plugin
- `audio_transcribe_any(file_path)` — beliebige Audiodatei → Text (ffmpeg + Vosk, offline)
- `audio_tts(text)` — Text → WAV-Sprachdatei (pyttsx3/SAPI5, offline)

### Neu: Moltbook Plugin
- `moltbook_get_feed`, `moltbook_create_post`, `moltbook_add_comment`
- Soziale Präsenz auf moltbook.com

### Neu: Dynamische Plugin-Übersicht
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

### Neu: start.bat — visuelles Redesign
- ASCII-Logo, ANSI-Farben (grün/gelb/rot), Box-Rahmen für jeden Schritt
- 6-stufige Fortschrittsanzeige mit ✓/!/✗ Symbolen
- Aktives Modell wird beim Start angezeigt
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

### Neu: [Feature-Name]
- Was wurde hinzugefügt und warum

### Geändert: [Was]
- Was und warum geändert

### Fix: [Was]
- Was war kaputt und wie gefixt
```
