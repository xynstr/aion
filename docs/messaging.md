# Messaging Channels

Each channel has fully isolated conversation history — no context bleeding between platforms.

## Telegram

Set token + whitelist in the Web UI (Settings → Telegram) or via CLI:
```
/telegram token 123456:ABC...
/telegram add 123456789
```

Or via `.env`:
```env
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

Supports: text, images, voice messages (transcription + TTS reply).

## Discord

```env
DISCORD_BOT_TOKEN=...
```

Responds to DMs and @mentions. Slash command `/ask`.
Enable **MESSAGE CONTENT INTENT** in the Discord Developer Portal.

## Slack

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

Socket Mode — no public webhook needed. Responds to DMs and @aion mentions.

## Amazon Alexa

`POST /api/alexa` — Alexa Skill endpoint. Configure the HTTPS endpoint in Alexa Developer Console.

---

# Audio

| Direction | What happens |
|-----------|-------------|
| Voice message → AION | Transcribed offline via Vosk + ffmpeg |
| AION → voice reply | TTS via edge-tts (Microsoft Neural) or pyttsx3 (offline) |
| `audio_tts` in Web UI | Audio player rendered directly in chat |
| Telegram voice | OGG OPUS via ffmpeg |
| Discord voice | MP3/WAV file attachment |

Configure in Web UI (System tab):
```env
# TTS options: edge (recommended), sapi5 (offline), pyttsx3
```

---

# Browser Automation

AION controls a real Chromium browser via Playwright:

| Tool | Action |
|------|--------|
| `browser_open(url)` | Load a page |
| `browser_screenshot()` | Capture full page |
| `browser_click(selector)` | Click by CSS selector |
| `browser_fill(selector, value)` | Fill input fields |
| `browser_get_text()` | Extract page text |
| `browser_evaluate(js)` | Run JavaScript |
| `browser_find(query)` | Natural language element search |
| `browser_close()` | Close the browser |

One-time setup:
```bash
pip install playwright
python -m playwright install chromium
```

Configure headless mode: `config.json → "browser_headless": true`

---

# MCP Client — 1,700+ Integrations

```bash
pip install mcp
npm install -g npx
```

Add servers to `mcp_servers.json` (no secrets — committable):

```json
{
  "servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "vault_env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "mcp_github"}
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "vault_env": {"POSTGRES_CONNECTION_STRING": "mcp_postgres"}
    }
  }
}
```

Store secrets in the encrypted vault:
```
credential_write("mcp_github", "ghp_your_token_here")
```

Tools are auto-discovered and registered as `mcp_{server}_{tool}` on startup.
