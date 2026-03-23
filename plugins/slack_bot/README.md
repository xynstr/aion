# slack_bot

Bidirectional Slack-Bot für AION via Socket Mode. App-Mentions + DMs, pro User eigene Session.

## Einrichtung

1. [Slack API](https://api.slack.com/apps) → Neue App → "From scratch"
2. **Socket Mode** aktivieren (App Settings → Socket Mode)
3. **App-Level Token** generieren (Scope: `connections:write`) → `SLACK_APP_TOKEN=xapp-...`
4. **OAuth & Permissions** → Bot Token Scopes hinzufügen:
   - `app_mentions:read`, `chat:write`, `im:history`, `im:read`, `im:write`
5. **Event Subscriptions** → Subscribe to bot events:
   - `app_mention`, `message.im`
6. App installieren → Bot User OAuth Token → `SLACK_BOT_TOKEN=xoxb-...`

`.env`:
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

## Features

- Antwortet auf @Mentions in Kanälen (antwortet im selben Thread)
- Antwortet auf Direktnachrichten
- Pro User eigene AION-Session (`slack_{user_id}`)
- Nachrichten automatisch gesplittet bei 3000 Zeichen

## Dependencies

```bash
pip install slack-bolt
```
