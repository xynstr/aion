# discord_bot

Bidirectional Discord bot for AION. Per-user sessions, @mention + DM support, slash commands.

## Einrichtung

1. [Discord Developer Portal](https://discord.com/developers/applications) → Neue Anwendung → Bot
2. Token kopieren → `.env`:
   ```
   DISCORD_BOT_TOKEN=dein_token_hier
   ```
3. **Privileged Gateway Intents** (im Dev Portal unter Bot → Intents): `MESSAGE CONTENT INTENT` aktivieren
4. Bot einladen: OAuth2 → URL Generator:
   - Scope: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Read Message History`, `Use Slash Commands`

## Features

- Responds to @mentions in channels
- Antwortet auf Direktnachrichten
- Slash-Command `/ask <frage>`
- Bildverarbeitung via Attachment-URLs
- Pro User eigene AION-Session (`discord_{user_id}`)
- Nachrichten automatisch gesplittet bei 1900 Zeichen

## Dependencies

```bash
pip install discord.py
```
