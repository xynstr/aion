# AION — Changelog

Hier steht was sich geändert hat. AION liest dieses Dokument beim Start und weiß so was neu ist.
**Pflicht:** Nach jeder Selbst-Modifikation (Code, Plugin, Config) einen Eintrag ergänzen.

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
