# telegram_bot

Bidirektionale Telegram-Integration für AION. Text, Bilder und Sprachnachrichten senden und empfangen.

## Zweck

AION antwortet auf Telegram-Nachrichten (Text, Bilder, Sprachnachrichten) und kann von sich aus Nachrichten und Audiodateien versenden. Jeder Telegram-User bekommt eine eigene AionSession mit History und Charakter-Update.

## Tools

| Tool | Beschreibung |
|---|---|
| `send_telegram_message(message)` | Text an konfigurierte Chat-ID senden. Markdown wird automatisch in Telegram-HTML konvertiert. Lange Nachrichten werden aufgeteilt. |
| `send_telegram_voice(path)` | Audiodatei als Telegram-Sprachnachricht senden. Akzeptiert WAV, MP3, OGG u.a. — konvertiert automatisch zu OGG OPUS via ffmpeg. |

## Workflow für Sprachnachricht senden

```
1. audio_tts(text)           → erzeugt WAV-Datei, gibt {ok, path} zurück
2. send_telegram_voice(path) → sendet WAV als Sprachnachricht (OGG-Konvertierung automatisch)
```

## Konfiguration

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
- Sprachnachrichten (OGG) → ffmpeg → Vosk-Transkription → AION → TTS-Rückantwort
- Bilder → Base64 → AION Vision

## Abhängigkeiten

| Paket | Zweck |
|---|---|
| `httpx` | HTTP-Requests zur Telegram API |
| `ffmpeg` | Audio-Konvertierung (WAV/MP3 → OGG OPUS) |
| `audio_pipeline` Plugin | TTS + Transkription |
