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

**Telegram Tools:**
| Tool | What it does |
|------|-------------|
| `send_telegram_message(text)` | Send text message with Markdown |
| `send_telegram_document(path, caption)` | Send any file (.docx, .pdf, .py, etc.) |
| `send_telegram_voice(path)` | Send audio file as voice message |
| `telegram_add_user(chat_id)` | Add user to allowlist |
| `telegram_list_users()` | List all allowed users |

**Supported message types:**
- ✅ Text (with Markdown formatting)
- ✅ Images (auto-sent when AION generates them)
- ✅ Voice messages (transcribed offline via Faster Whisper)
- ✅ Documents & files (any format)
- ✅ Voice replies (TTS via edge-tts or pyttsx3)

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
| Voice message → AION | Transcribed offline via **Faster Whisper** (multilingual, no API keys) |
| AION → voice reply | TTS via **edge-tts** (Microsoft Neural, recommended) or **pyttsx3** (offline) |
| `audio_transcribe_any` tool | Transcribe any audio file format |
| `audio_tts` tool | Convert text to speech, save as file |
| Telegram voice | OGG OPUS via ffmpeg (auto-converted if needed) |
| Discord voice | MP3/WAV file attachment |

**STT (Speech-to-Text):**
- Fully offline, no API keys needed
- Supports OGG, MP3, WAV, M4A, FLAC, WebM
- Auto-detects language
- Model size: small (~465 MB), medium, large-v3

**TTS (Text-to-Speech):**
- Configure in Web UI (System tab) or config.json
- Default: `edge` (best quality, requires internet)
- Fallback: `sapi5` on Windows, `pyttsx3` on all platforms
```json
{
  "tts_engine": "edge",
  "tts_voice": "de-DE-KatjaNeural"
}
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
