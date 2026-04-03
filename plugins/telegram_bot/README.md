# telegram_bot

Bidirektionale Telegram-Integration für AION. Text, Bilder und Sprachnachrichten senden und empfangen.

## Zweck

AION antwortet auf Telegram-Nachrichten (Text, Bilder, Sprachnachrichten) und kann von sich aus Nachrichten und Audiodateien versenden. Jeder Telegram-User bekommt eine eigene AionSession mit History und Charakter-Update.

## Tools

| Tool | Beschreibung |
|---|---|
| `send_telegram_message(message)` | Text an konfigurierte Chat-ID senden. Markdown wird automatisch in Telegram-HTML konvertiert. Lange Nachrichten werden aufgeteilt. |
| `send_telegram_document(path, caption?)` | **Beliebige Dateien senden** — .docx, .pdf, .txt, .py, .zip usw. Akzeptiert jeden Dateityp, Telegram speichert diese cloud-seitig. Optionaler Begleittext. |
| `send_telegram_voice(path)` | Audiodatei als Telegram-Sprachnachricht senden. Akzeptiert WAV, MP3, OGG u.a. — konvertiert automatisch zu OGG OPUS via ffmpeg. |
| `telegram_add_user(chat_id)` | Benutzer zur Whitelist hinzufügen. |
| `telegram_list_users()` | Alle erlaubten Chat-IDs auflisten. |

## Workflows

**Text senden:**
```
send_telegram_message("Hallo Welt")
```

**Datei senden (z.B. Word-Dokument):**
```
send_telegram_document(
  path="/path/to/file.docx",
  caption="Hier ist das Konzept"
)
```

**Sprachnachricht als Antwort senden:**
```
1. audio_tts(text)           → erzeugt WAV-Datei, gibt {ok, path} zurück
2. send_telegram_voice(path) → sendet WAV als Sprachnachricht (OGG-Konvertierung automatisch)
```

## Configuration

In `.env`:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPqrstuvwxyz
TELEGRAM_CHAT_ID=987654321
```

**Bot erstellen:**
1. [@BotFather](https://t.me/BotFather) öffnen → `/newbot`
2. Token in `.env` eintragen
3. `/start` an den Bot senden → Chat-ID wird automatisch gespeichert

## Empfang (Polling)

- Daemon-Thread läuft im Hintergrund, startet automatisch beim Plugin-Load
- Nachrichten werden an eine eigene `AionSession(channel="telegram_{chat_id}")` weitergeleitet
- **Sprachnachrichten:** OGG → **Faster Whisper** (offline, multilingual) → Text → AION → TTS-Rückantwort
- **Bilder:** → Base64 → AION Vision
- **Dateien:** werden mit Caption gespeichert, können in Gespräch kontextualisiert werden

## Dependencies

| Paket | Zweck |
|---|---|
| `httpx` | HTTP-Requests zur Telegram API |
| `ffmpeg` | Audio-Konvertierung (optional, aber empfohlen für Audio) |
| `audio_pipeline` Plugin | TTS (Text-to-Speech) + STT (Faster Whisper) |
| `faster-whisper` | Spracherkennung (via audio_pipeline, offline) |

**Optional — für besseres Audio-Format-Support:**
```bash
winget install Gyan.FFmpeg  # Windows
brew install ffmpeg         # macOS
apt install ffmpeg          # Linux
```
