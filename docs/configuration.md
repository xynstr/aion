# Configuration

## Environment Variables (`.env`)

```env
# At least one provider key is required
GEMINI_API_KEY=AIza...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
XAI_API_KEY=xai-...

# Active model (also changeable via Web UI)
AION_MODEL=gemini-2.5-flash

# Messaging (optional)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
DISCORD_BOT_TOKEN=...
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# Web server (optional)
AION_PORT=7000
AION_HOST=127.0.0.1   # use 0.0.0.0 for LAN access

# Auto-updates (optional)
AION_GITHUB_REPO=xynstr/aion
```

## config.json

Managed via Web UI (System tab) or `aion config set <key> <value>`.

| Key | Default | Description |
|-----|---------|-------------|
| `model` | `gemini-2.5-flash` | Active LLM model |
| `check_model` | *(unset)* | Model for internal YES/NO completion checks |
| `max_history_turns` | `40` | Conversation history limit |
| `tts_engine` | `edge` | TTS engine: `edge`, `sapi5`, `pyttsx3`, `off` |
| `tts_voice` | *(provider default)* | TTS voice name |
| `thinking_level` | `standard` | Reasoning depth: `off / minimal / standard / deep / extreme` |
| `browser_headless` | `true` | Playwright headless mode |
| `tool_tier` | `1` | Tool schema verbosity: `1` = core only, `2` = all |
| `web_auth_token` | *(unset)* | Bearer token for Web UI (set by web_tunnel plugin) |

## Task Routing

Route tasks to the best model automatically:

```json
"task_routing": {
  "coding":   "claude-opus-4-6",
  "review":   "claude-sonnet-4-6",
  "browsing": "gemini-2.5-flash",
  "default":  "gemini-2.5-pro"
}
```

Configure via Web UI (System → Task Routing) or in chat:
```
"Use Claude for coding, Gemini for everything else"
```

## File Structure

```
aion/
├── aion.py                      # Core: memory, LLM loop, tool dispatch
├── aion_web.py                  # Web server (FastAPI + SSE)
├── aion_cli.py                  # CLI mode
├── aion_launcher.py             # Entry point (aion command)
├── plugin_loader.py             # Plugin loading + hot-reload
├── config_store.py              # Thread-safe config I/O
├── static/index.html            # Web UI (Vanilla JS, no build step)
├── plugins/                     # All plugins (one folder per plugin)
├── prompts/rules.md             # System prompt / behavioral rules
├── character.md                 # AION's personality (evolves automatically)
├── AION_SELF.md                 # Technical self-documentation
├── aion_memory.json             # Persistent memory (max 300 entries)
├── conversation_history.jsonl   # Full conversation history
├── config.json                  # Active settings
└── .env                         # API keys (git-ignored)
```

## Troubleshooting

| Problem | Solution |
|---------|---------|
| Menu shows raw ANSI codes | Run `aion update` — VT100 is auto-enabled on Windows |
| `aion --setup` does nothing | `pip install -r requirements.txt && pip install -e .` first |
| `No module named 'google'` | `pip install google-genai` |
| Plugin not loading | Check `aion_events.log` — usually a missing `pip install` |
| Port already in use | Set `AION_PORT=7001` in `.env` |
| Playwright not found | `python -m playwright install chromium` |
| ffmpeg not in PATH | Add ffmpeg to PATH or install via winget |
| Voice messages not working | Install ffmpeg + set `tts_engine=edge` in config |
| Discord/Slack bot silent | Check token + intents/permissions in developer portal |

Log files: `aion_events.log`, `aion_start.log`
