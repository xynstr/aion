# AION — Autonomous Intelligent Operations Node

An autonomous AI agent. Runs as a Python process, communicates via LLM APIs, executes tools, learns, and can modify itself.

---

## Features

- **Autonomous operation** — up to 50 tool iterations without waiting for the user, with automatic completion check + task enforcer
- **Scheduled tasks** — scheduler with fixed times (`06:00`) and intervals (`every 5m`) — runs fully autonomously
- **Self-modification** — reads, patches, and overwrites its own code; creates new plugins
- **Web UI** — live stream of responses, thoughts, and tool calls; persistent sidebar navigation (Chat / Prompts / Plugins / Memory / System)
- **CLI mode** — fully without browser/server: `aion --cli`; color terminal output with tool/thought display
- **Multi-provider** — Gemini, OpenAI, Anthropic Claude, DeepSeek, Grok, Ollama (local) — any OpenAI-compatible API works via a simple plugin
- **Model Failover** — if the primary model API fails, AION automatically tries available fallback models
- **Telegram** — bidirectional: text, images, voice messages (OGG → Vosk transcription, TTS reply)
- **Discord** — per-user sessions, DMs + @mentions + `/ask` slash command
- **Slack** — Socket Mode, DMs + @aion mentions, per-user sessions
- **Amazon Alexa** — Alexa Skill endpoint (`POST /api/alexa`) for voice control
- **Browser automation** — Playwright plugin: open pages, click, fill forms, screenshot, evaluate JS
- **Multi-agent routing** — delegate subtasks to isolated sub-agents
- **Memory** — persistent JSON memory + conversation history (JSONL) with channel filtering
- **Personality** — `character.md` evolves through conversations; auto-updates every 5 conversations
- **Plugin system** — `plugins/<name>/<name>.py` loaded automatically; custom HTTP routes without touching core
- **Audio pipeline** — any audio format → transcription (ffmpeg + Vosk, offline) + TTS (edge-tts / pyttsx3)
- **Docker** — one-command deployment via `docker-compose up`

---

## Requirements

- Python 3.10+
- At least one API key: Gemini, OpenAI, Anthropic, DeepSeek, or Grok — or a local Ollama server

---

## Installation

```bash
pip install -r requirements.txt
pip install -e .          # installs the 'aion' command globally
```

Or use the guided setup:

```bash
aion --setup
```

---

## Starting

```bash
aion                      # Web server + opens browser (port 7000)
aion --cli                # Interactive CLI (no browser)
aion --setup              # Guided onboarding wizard
docker-compose up         # Docker deployment
```

---

## Configuration

Create a `.env` file in the project directory:

```env
GEMINI_API_KEY=AIza...              # Google Gemini
OPENAI_API_KEY=sk-...               # OpenAI
ANTHROPIC_API_KEY=sk-ant-...        # Anthropic Claude
DEEPSEEK_API_KEY=sk-...             # DeepSeek
XAI_API_KEY=xai-...                 # xAI Grok
# Ollama: no key needed — local server at localhost:11434
TELEGRAM_BOT_TOKEN=1234...:AAE...   # optional
TELEGRAM_CHAT_ID=123456789          # optional
DISCORD_BOT_TOKEN=...               # optional
SLACK_BOT_TOKEN=xoxb-...            # optional
SLACK_APP_TOKEN=xapp-...            # optional
AION_MODEL=gemini-2.5-flash         # optional, default: gpt-4.1
AION_PORT=7000                      # optional, default: 7000
AION_HOST=127.0.0.1                 # optional, default: 127.0.0.1 (use 0.0.0.0 for LAN access)
```

The active model is stored in `config.json` and restored on the next start.

---

## Web UI

Opens automatically at `http://localhost:7000`

```
┌────────────────────────────────────────────────────────────────┐
│  ●  AION          [Model ▼]  [Save]               [↺ Reset]   │
├──────────┬─────────────────────────────────────────────────────┤
│          │                                                     │
│ 💬 Chat  │   ACTIVE PAGE                                       │
│ 📝 Prompts   (switches based on sidebar selection)            │
│ 🔌 Plugins                                                     │
│ 🧠 Memory│   Chat: token streaming, thoughts + tool calls     │
│ ⊞ System │         as inline accordions (correct order)       │
│          │                                                     │
│          ├─────────────────────────────────────────────────────┤
│          │   [Input…]                                [▶]       │
└──────────┴─────────────────────────────────────────────────────┘
```

**Sidebar** (172px, always visible):
- **💬 Chat** — token streaming; thoughts + tool calls inline as expandable accordions (in correct order)
- **📝 Prompts** — edit `prompts/rules.md`, `character.md`, `AION_SELF.md` directly in the browser
- **🔌 Plugins** — all plugins with tools + status + hot-reload
- **🧠 Memory** — search memory, color-coded, delete entries
- **⊞ System** — statistics, model switching, TTS settings, model fallback, paths, actions

---

## CLI Mode

```
aion --cli

  ╔══════════════════════════════════════╗
  ║  AION  —  CLI Mode                   ║
  ╚══════════════════════════════════════╝

  Initializing AION… OK
  Model: gemini-2.5-flash  |  Tools: 56

You  › list the files in the project directory
  ⚙  shell_exec({'command': 'dir /b'})  → OK aion.py aion_web.py ...
AION › Here are the files in the directory: ...

You  › exit
  Session ended. Goodbye!
```

- Thoughts appear as `💭 …` in purple
- Tool calls as `⚙ tool(args) → OK/ERR result` in yellow/gray
- Responses as `AION › …` live-streamed in cyan
- Internal commands: `/help`, `/clear`, `/model`

---

## Messaging Channels

### Telegram
1. Create a bot via [@BotFather](https://t.me/BotFather) → token
2. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
3. Start AION — Telegram polling starts automatically

### Discord
1. Create a bot at [discord.com/developers](https://discord.com/developers)
2. Enable **MESSAGE CONTENT INTENT** in the bot settings
3. Set `DISCORD_BOT_TOKEN` in `.env`

### Slack
1. Create a Slack App with **Socket Mode** enabled
2. Add `app_mentions:read`, `im:history`, `chat:write` scopes
3. Set `SLACK_BOT_TOKEN` (xoxb-) and `SLACK_APP_TOKEN` (xapp-) in `.env`

Each channel has isolated conversation history (no cross-channel context bleed).

---

## Browser Automation

AION can control a Chromium browser via the `playwright_browser` plugin:

```
browser_open        → open a URL
browser_screenshot  → capture page or element
browser_click       → click by CSS selector
browser_fill        → fill input fields
browser_get_text    → extract text
browser_evaluate    → run JavaScript
browser_find        → natural language element search
browser_close       → close browser
```

Setup (one-time, handled automatically in onboarding):
```bash
pip install playwright
python -m playwright install chromium
```

Configure headless mode in `config.json`: `"browser_headless": true`

---

## Scheduled Tasks

```
"Schedule daily at 06:00: Read my emails, extract appointments."
"Send me a Telegram message every 5 minutes with the current status."
"Remind me every hour to drink water."
```

**Interval syntax:** `"5m"`, `"30s"`, `"1h"`, `"2h30m"`, `"every 10 minutes"`

Manage directly:
- `schedule_list` — show all tasks
- `schedule_remove` — delete a task
- `schedule_toggle` — enable/disable a task

---

## Docker

```bash
docker-compose up
```

Mounts `.env`, `config.json`, memory, logs, and plugins as volumes. Playwright/Chromium pre-installed. Restarts automatically unless stopped.

---

## Creating a Plugin

Every file at `plugins/<name>/<name>.py` must have a `register(api)` function:

```python
def register(api):
    def my_tool(param: str = "", **_) -> dict:
        return {"ok": True, "result": param}

    api.register_tool(
        name="my_tool",
        description="Description for the LLM",
        func=my_tool,
        input_schema={
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "..."}
            },
            "required": ["param"]
        }
    )
```

**Important:** Use keyword args `def fn(param: str = "", **_)` — not `def fn(input: dict)`.

Plugins can also provide HTTP routes without touching `aion_web.py`:

```python
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/myplugin/status")
async def status():
    return {"ok": True}

def register(api):
    api.register_tool(...)
    api.register_router(router, tags=["myplugin"])
```

AION can also create plugins at runtime via the `create_plugin` tool.

---

## Web API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Server status, model, uptime |
| POST | `/api/chat` | Send a chat message (SSE stream) |
| POST | `/api/model` | Switch model |
| GET | `/api/plugins` | All plugins with tools + load status |
| POST | `/api/plugins/reload` | Hot-reload plugins |
| GET | `/api/memory` | Memory entries (`?search=`, `?limit=`, `?offset=`) |
| DELETE | `/api/memory` | Clear memory |
| GET | `/api/providers` | All registered LLM providers + active model |
| GET | `/api/config` | Configuration + statistics |
| POST | `/api/config/settings` | Update settings (TTS, model_fallback, browser_headless) |
| GET | `/api/prompt/{name}` | Read prompt (`rules`, `character`, `self`) |
| POST | `/api/prompt/{name}` | Save prompt |
| GET | `/api/oauth/google/start` | Begin Google OAuth flow for Gemini |
| GET | `/api/oauth/google/callback` | OAuth callback |
| POST | `/api/alexa` | Amazon Alexa Skill endpoint |

---

## File Structure

```
AION/
├── aion.py                      # Core logic: memory, tools, LLM loop, AionSession
├── aion_web.py                  # Web server (FastAPI + SSE), port 7000
├── aion_cli.py                  # CLI mode: interactive terminal without browser
├── onboarding.py                # Guided setup wizard (aion --setup)
├── plugin_loader.py             # Loads plugins + register_router support
├── static/index.html            # Web UI (Vanilla JS, persistent sidebar)
├── Dockerfile                   # Docker image
├── docker-compose.yml           # Docker Compose config
├── plugins/
│   ├── core_tools/              # continue_work, read_self_doc, system_info, memory_record
│   ├── shell_tools/             # shell_exec, winget_install, install_package
│   ├── web_tools/               # web_search, web_fetch
│   ├── scheduler/               # Cron scheduler
│   ├── telegram_bot/            # Telegram: text + images + voice
│   ├── discord_bot/             # Discord: DMs + @mentions + /ask
│   ├── slack_bot/               # Slack: Socket Mode, DMs + mentions
│   ├── alexa_plugin/            # Amazon Alexa Skill endpoint
│   ├── playwright_browser/      # Browser automation (8 tools)
│   ├── multi_agent/             # Sub-agent delegation (4 tools)
│   ├── gemini_provider/         # Google Gemini (prefix "gemini")
│   ├── anthropic_provider/      # Anthropic Claude (prefix "claude")
│   ├── deepseek_provider/       # DeepSeek (prefix "deepseek")
│   ├── grok_provider/           # xAI Grok (prefix "grok")
│   ├── ollama_provider/         # Local Ollama (prefix "ollama/")
│   ├── memory_plugin/           # Conversation history (JSONL, channel-aware)
│   ├── audio_pipeline/          # Audio transcription + TTS
│   ├── heartbeat/               # Keep-alive + autonomous todo processing
│   ├── todo_tools/              # Task management
│   ├── smart_patch/             # Fuzzy code patching
│   ├── image_search/            # Image search (Openverse + Bing)
│   ├── docx_tool/               # Create Word documents
│   └── moltbook/                # Social platform moltbook.com
├── character.md                 # Personality (self-updating)
├── AION_SELF.md                 # Technical self-documentation for AION
├── aion_memory.json             # Persistent memory (max. 300 entries)
├── conversation_history.jsonl   # Full conversation history
├── thoughts.md                  # Recorded thoughts
├── .env                         # API keys (not in Git)
└── config.json                  # Active model + settings
```

---

## Available Models

| Provider | Model | Notes |
|----------|-------|-------|
| Google Gemini | `gemini-2.5-pro` | Best quality |
| Google Gemini | `gemini-2.5-flash` | Fast & affordable |
| Google Gemini | `gemini-2.5-flash-lite` | Lightweight |
| Google Gemini | `gemini-2.0-flash` | Stable |
| OpenAI | `gpt-4.1` | OpenAI flagship |
| OpenAI | `gpt-4.1-mini` | Affordable |
| OpenAI | `gpt-4o` | Multimodal |
| OpenAI | `o3` | Reasoning |
| OpenAI | `o4-mini` | Fast reasoning |
| Anthropic | `claude-opus-4-6` | Most capable Claude |
| Anthropic | `claude-sonnet-4-6` | Balanced |
| Anthropic | `claude-haiku-4-5-20251001` | Fastest Claude |
| DeepSeek | `deepseek-chat` | Efficient & affordable |
| DeepSeek | `deepseek-reasoner` | Reasoning |
| Grok (xAI) | `grok-3` | xAI flagship |
| Grok (xAI) | `grok-3-mini` | Fast |
| Ollama (local) | `ollama/llama3.2` | No internet needed |
| Ollama (local) | `ollama/qwen2.5` | Multilingual |
| Ollama (local) | `ollama/deepseek-r1:8b` | Local reasoning |

Switch via Web UI (System tab → model dropdown) or by voice: `"Switch to claude-sonnet-4-6"`

---

## Security

- `.env` is in `.gitignore` — never commit API keys
- Web server binds to `127.0.0.1` by default (LAN access: set `AION_HOST=0.0.0.0`)
- `shell_exec` runs arbitrary shell commands — use only on trusted systems
- `self_modify_code` / `self_patch_code` — AION asks for confirmation before making code changes
- Scheduler tasks run with full AION permissions — formulate tasks carefully

---

## Troubleshooting

**Plugin not loading:** Check `aion_events.log` for the error. Common cause: missing dependency (`pip install <package>`).

**Provider not available:** Check `.env` for the correct API key variable name.

**Discord / Slack bot silent:** Confirm the token is set in `.env` and the bot has the required permissions/intents.

**Playwright not found:** Run `python -m playwright install chromium`.

**Port already in use:** Set `AION_PORT=7001` in `.env`.
