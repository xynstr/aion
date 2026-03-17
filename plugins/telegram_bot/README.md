# Plugin: telegram_bot

**Bidirektionale Telegram-Integration**

## Funktion

AION antwortet auf Telegram-Nachrichten und kann Nachrichten an Telegram senden. Nutzt `python-telegram-bot` für Polling und `requests` für das Senden.

## Tools

### `send_telegram_message`

**Parameter:**
- `message` (string): Nachricht zum Senden

**Ausgabe:**
- `ok` (boolean): Erfolgreich gesendet?
- `error` (string): Fehlermeldung falls Problem

## Konfiguration

In `.env`:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPqrstuvwxyz
TELEGRAM_CHAT_ID=987654321
```

**So bekommst du einen Bot:**
1. Öffne [@BotFather](https://t.me/BotFather) in Telegram
2. Sende `/newbot`
3. Folge den Anweisungen
4. Kopiere Token in `.env`

**Chat-ID speichern:**
1. Bot starten
2. Sende `/start` an den Bot
3. Chat-ID wird automatisch gespeichert

## Funktionsweise

### Empfangen (Polling)
- Daemon-Thread wartet auf neue Nachrichten
- Startet automatisch beim Plugin-Load (wenn Token vorhanden)
- Ruft `run_aion_turn` mit Nachricht auf
- Sendet Antwort zurück

### Senden
- `send_telegram_message` nutzt HTTP-Request (keine asyncio nötig)
- Sendung an gespeicherte Chat-ID
- Max. 4000 Zeichen pro Nachricht

## Beispiel

```
Du schreibst auf Telegram:
"Was ist 2+2?"

→ Plugin empfängt Nachricht
→ run_aion_turn("Was ist 2+2?", "telegram")
→ AION beantwortet
→ Antwort wird zurück zu Telegram gesendet
```
