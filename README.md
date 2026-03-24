<div align="center">

<img src="static/aion-2026.svg" alt="AION" width="400">

**Autonomous Intelligent Operations Node**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688?style=flat-square)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![Platforms](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)]()

</div>

---

AION is a self-contained autonomous AI agent that runs as a Python process on your machine.
It streams responses live, executes tools, schedules tasks, controls a browser, sends messages across platforms — and can read, patch, and extend its own code.

> **No cloud dependency beyond the LLM API.** Everything else runs locally.

---

## ✦ What makes AION different

| Feature | AION | Typical chatbot |
|---------|------|----------------|
| Runs tools autonomously (up to 50 iterations) | ✅ | ❌ |
| Modifies its own code and creates plugins | ✅ | ❌ |
| Schedules tasks that run while you're away | ✅ | ❌ |
| Controls a real browser (Playwright) | ✅ | ❌ |
| Works via Telegram, Discord, Slack, Alexa | ✅ | ❌ |
| Multi-provider with automatic failover | ✅ | ❌ |
| Use Claude subscription instead of API key | ✅ | ❌ |
| Personality that evolves through conversation | ✅ | ❌ |
| 100% local memory + history | ✅ | ❌ |

---

## ⚡ Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e .

# Guided setup (recommended for first run)
aion --setup

# Start — interactive selector (Web UI or CLI)
aion

# Or start directly
aion --web    # Web UI → http://localhost:7000
aion --cli    # CLI mode (terminal only)

# Update to the latest version (git pull + reinstall)
aion update
```

`aion` shows an arrow-key selector on every start. Pick **Web UI** or **CLI** with ↑↓ + Enter.

---

## 🤖 Supported AI Providers

AION supports multiple providers simultaneously. Switch between them at any time — even mid-conversation.

### Using an API Key

| Provider | Key | Best for | Cost |
|----------|-----|----------|------|
| **Google Gemini** | `GEMINI_API_KEY` | Speed, multimodal, free tier | Free / pay-per-use |
| **OpenAI** | `OPENAI_API_KEY` | GPT-4.1, o3, o4-mini | Pay-per-use |
| **Anthropic Claude** | `ANTHROPIC_API_KEY` | Code, reasoning | Pay-per-use |
| **DeepSeek** | `DEEPSEEK_API_KEY` | Affordable reasoning | Very low cost |
| **xAI Grok** | `XAI_API_KEY` | Latest xAI models | Pay-per-use |
| **Ollama** | *(none)* | Fully local, offline | Free |

### Using a Subscription (no API key needed)

| Provider | How | Plan |
|----------|-----|------|
| **Google Gemini** | Google OAuth flow — built into the Keys tab | Google Cloud |
| **Anthropic Claude** | Claude Code CLI (`claude login`) — built into onboarding | claude.ai $20/$200 |

> **Tip:** Use Gemini Flash (free) for everyday tasks and Claude Opus (subscription) for complex coding — configured via Task Routing.

---

## 🔐 Credentials Vault

AION includes a built-in encrypted vault for storing API keys, passwords, and login data per service.

```
credentials/
├── facebook.md.enc       ← AES-encrypted markdown per service
├── openai.md.enc
├── telegram.md.enc
└── .vault.key            ← encryption key (never commit this)
```

The entire `credentials/` folder is **gitignored**. Files are encrypted with Fernet (AES-128-CBC + HMAC-SHA256).

**Usage — just tell AION:**
- *"Save my Facebook credentials: email foo@bar.com, password 1234"*
- *"What are my OpenAI credentials?"*
- *"Show all saved credentials"*
- *"Delete my Telegram credentials"*

AION automatically calls `credential_write`, `credential_read`, `credential_list`, or `credential_delete`.

> ⚠️ Back up your `credentials/` folder and `.vault.key` regularly. Without the key, encrypted files cannot be recovered.

---

## 📦 Installation

### Option A — Guided Setup (recommended)

```bash
pip install -r requirements.txt
pip install -e .
aion --setup
```

The setup wizard configures your API keys, messaging channels, browser mode, and — optionally — Claude subscription login. Everything can be changed later via the Web UI.

### Option B — Manual

```bash
pip install -r requirements.txt
```

Create `.env` in the project directory:

```env
# At least one provider key is required
GEMINI_API_KEY=AIza...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
XAI_API_KEY=xai-...

# Active model (also changeable via Web UI)
AION_MODEL=gemini-2.5-flash

# Auto-updates (optional) — checks GitHub Releases once per day
AION_GITHUB_REPO=xynstr/aion

# Messaging (optional)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
DISCORD_BOT_TOKEN=...
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# Web server (optional)
AION_PORT=7000
AION_HOST=127.0.0.1   # use 0.0.0.0 for LAN access
```

Then start:

```bash
python aion_web.py      # Web UI at http://localhost:7000
python aion_cli.py      # CLI mode (no browser)
```

### Option C — Docker

```bash
docker-compose up
```

Playwright/Chromium pre-installed. Volumes for `.env`, config, memory, logs, and plugins. Restarts automatically.

---

## 🖥 Web UI

```
┌────────────────────────────────────────────────────────────┐
│  ◈ AION   [gemini-2.5-pro ▼]  [Save]          [↺ Reset]   │
├──────────┬─────────────────────────────────────────────────┤
│          │                                                  │
│ 💬 Chat  │  Token streaming — responses appear live        │
│ 📝 Prompts  Thoughts 💭 and tool calls ⚙ inline          │
│ 🔑 Keys  │  Images and audio rendered directly in chat     │
│ 🔌 Plugins                                                  │
│ 🧠 Memory│                                                  │
│ ⊞ System │                                                  │
│          ├─────────────────────────────────────────────────┤
│          │  [Type a message…]                      [▶]     │
└──────────┴─────────────────────────────────────────────────┘
```

**Sidebar tabs:**

| Tab | What you get |
|-----|-------------|
| 💬 **Chat** | Live token streaming, thoughts + tool calls as inline accordions, image + audio rendering |
| 📝 **Prompts** | Edit `rules.md`, `character.md`, `AION_SELF.md` directly in the browser |
| 🔑 **Keys** | Set API keys per provider, Google OAuth, Claude subscription login — all with status indicators |
| 🔌 **Plugins** | All loaded plugins, tool list, hot-reload |
| 🧠 **Memory** | Searchable memory entries, color-coded, deletable |
| ⊞ **System** | Model switching, TTS settings, Task Routing, statistics, actions |

---

## 💻 CLI Mode

```bash
aion --cli

  ╔══════════════════════════════════════╗
  ║  AION  —  CLI Mode                   ║
  ╚══════════════════════════════════════╝
  Model: gemini-2.5-flash  |  Tools: 56

You  › Search for recent AI news and summarize the top 3
  💭  Performing web search for recent AI developments
  ⚙   web_search({query: "AI news 2026"})  →  OK  5 results
  ⚙   web_fetch({url: "..."})              →  OK  8420 chars
AION › Here are the top 3 AI stories this week: ...

You  › /model gemini-2.5-pro
  Model switched to gemini-2.5-pro
```

Internal commands: `/help`, `/clear`, `/model <name>`

---

## 🔀 Task Routing

Automatically route tasks to the best model:

```json
// config.json
"task_routing": {
  "coding":   "claude-opus-4-6",
  "review":   "claude-sonnet-4-6",
  "browsing": "gemini-2.5-flash",
  "default":  "gemini-2.5-pro"
}
```

AION reads this config and uses `ask_claude` automatically for code tasks — delegating to Claude while keeping all tool execution on the primary model.

Configure via Web UI (System tab) or in chat:
```
"Use Claude for coding, Gemini for everything else"
→ set_task_routing(coding="claude-opus-4-6", default="gemini-2.5-flash")
```

---

## 📱 Messaging Channels

Each channel has fully isolated conversation history — no context bleeding between platforms.

### Telegram
```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```
Supports: text, images, voice messages (transcription + TTS reply)

### Discord
```env
DISCORD_BOT_TOKEN=...
```
Responds to DMs and @mentions. Slash command `/ask`. Enable **MESSAGE CONTENT INTENT** in Discord Developer Portal.

### Slack
```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```
Socket Mode — no public webhook needed. Responds to DMs and @aion mentions.

### Amazon Alexa
`POST /api/alexa` — Alexa Skill endpoint. Configure the HTTPS endpoint in Alexa Developer Console.

---

## 🌐 Browser Automation

AION controls a real Chromium browser via Playwright:

```
"Open example.com, take a screenshot and send it to Telegram"

→ browser_open("https://example.com")
→ browser_screenshot()           ← image shown in chat + sent to Telegram
→ send_telegram_message(...)
```

**Available tools:**

| Tool | Action |
|------|--------|
| `browser_open(url)` | Load a page |
| `browser_screenshot()` | Capture full page or element |
| `browser_click(selector)` | Click by CSS selector |
| `browser_fill(selector, value)` | Fill input fields |
| `browser_get_text()` | Extract page text |
| `browser_evaluate(js)` | Run JavaScript |
| `browser_find(query)` | Natural language element search |
| `browser_close()` | Close the browser |

One-time setup (handled automatically in `aion --setup`):
```bash
pip install playwright
python -m playwright install chromium
```

Configure headless/visible: `config.json → "browser_headless": true`

---

## ⏰ Scheduled Tasks

```
"Every morning at 07:00: Check the weather and send me a summary via Telegram"
"Remind me every 30 minutes to take a break"
"Run a system health check every hour"
```

**Interval syntax:** `5m`, `30s`, `1h`, `2h30m`
**Fixed time syntax:** `07:00`, `daily`, `weekdays`, `mo,we,fr`

Manage via tools or in natural language:
```
schedule_list()    → show all tasks
schedule_remove()  → delete a task
schedule_toggle()  → enable/disable
```

---

## 🔊 Audio

AION handles audio in all directions:

| Direction | What happens |
|-----------|-------------|
| Voice message → AION | Transcribed offline via Vosk + ffmpeg |
| AION → voice reply | TTS via edge-tts (Microsoft Neural) or pyttsx3 (offline) |
| `audio_tts` in Web UI | Audio player rendered directly in chat |
| Telegram voice | OGG OPUS via ffmpeg |
| Discord voice | MP3/WAV file attachment |

Configure TTS engine and voice in Web UI (System tab) or `.env`:
```env
# TTS options: edge (recommended), sapi5 (offline), pyttsx3
```

---

## 🤖 Multi-Agent Routing

Delegate complex tasks to isolated sub-agents:

```python
delegate_to_agent("Research the top 5 Python web frameworks and compare them")
→ spawns a new AionSession with its own history
→ returns the result to the calling agent
```

Tools: `delegate_to_agent`, `sessions_list`, `sessions_send`, `sessions_history`

Sub-agents have isolated memory and history. Recursion guard prevents infinite loops.

---

## 🔧 Self-Modification

AION can read, patch, and overwrite its own code:

```
"Add a tool that checks the current Bitcoin price"
→ AION reads existing plugins for reference
→ creates plugins/btc_price/btc_price.py
→ hot-reloads without restarting
→ new tool immediately available
```

**Code editing tools:**
- `file_replace_lines` — replace exact line range (preferred)
- `self_patch_code` — find-and-replace block
- `self_modify_code` — overwrite entire file
- `create_plugin` — scaffold new plugin with auto-generated README
- `self_restart` — hot-reload plugins without process restart
- `restart_with_approval` — full process restart (with user confirmation)

---

## 🧩 Plugin Development

Every plugin lives in `plugins/<name>/<name>.py` and exports a `register(api)` function:

```python
# plugins/my_plugin/my_plugin.py

def register(api):
    def my_tool(param: str = "", **_) -> dict:
        """What this tool does — shown in the system prompt."""
        return {"ok": True, "result": f"processed: {param}"}

    api.register_tool(
        name="my_tool",
        description="Short description for the LLM",
        func=my_tool,
        input_schema={
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "Input parameter"}
            },
            "required": ["param"]
        }
    )
```

**Important:** Always use keyword args — `def fn(param: str = "", **_)`, never `def fn(input: dict)`.

Plugins can also expose HTTP routes without touching core:

```python
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/myplugin/status")
async def status():
    return {"ok": True, "plugin": "myplugin"}

def register(api):
    api.register_tool(...)
    api.register_router(router, tags=["myplugin"])
```

Hot-reload: `POST /api/plugins/reload` or **🔌 Plugins → ↺ Reload** in the Web UI.

---

## 🌐 REST API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/status` | Server status, model, uptime |
| `POST` | `/api/chat` | Chat (SSE stream: `token`, `thought`, `tool_result`, `approval`, `done`) |
| `POST` | `/api/reset` | Reset conversation |
| `POST` | `/api/model` | Switch active model |
| `GET` | `/api/providers` | All registered providers + active model |
| `GET` | `/api/plugins` | All plugins with tools + load status |
| `POST` | `/api/plugins/reload` | Hot-reload all plugins |
| `GET` | `/api/keys` | API keys (masked) grouped by provider |
| `POST` | `/api/keys` | Save key to `.env` + update running process |
| `GET` | `/api/memory` | Memory entries (`?search=`, `?limit=`, `?offset=`) |
| `DELETE` | `/api/memory` | Clear all memory |
| `GET` | `/api/config` | Configuration + statistics |
| `POST` | `/api/config/settings` | Update settings (TTS, model_fallback, task_routing, …) |
| `GET` | `/api/prompt/{name}` | Read a prompt file (`rules`, `character`, `self`) |
| `POST` | `/api/prompt/{name}` | Save a prompt file |
| `GET` | `/api/audio/{filename}` | Stream a generated audio file |
| `GET` | `/api/claude-cli/status` | Claude CLI install + auth status |
| `POST` | `/api/claude-cli/login` | Start Claude subscription login (opens browser) |
| `GET` | `/api/oauth/google/start` | Begin Google OAuth for Gemini |
| `GET` | `/api/oauth/google/callback` | OAuth callback handler |
| `POST` | `/api/alexa` | Amazon Alexa Skill endpoint |
| `GET` | `/api/update-status` | Current update state (version, available, release URL) |
| `POST` | `/api/update-trigger` | Force an immediate update check |

SSE events from `/api/chat`:

```
token          → partial text chunk (stream live)
thought        → AION's inner monologue
tool_call      → tool being called (name + args)
tool_result    → tool result (ok/error)
approval       → awaiting user confirmation (Ja/Nein buttons)
done           → full_response, response_blocks (images + audio), approval_pending
error          → error message
```

---

## 📁 File Structure

```
AION/
├── aion.py                      # Core: memory, LLM loop, tool dispatch, AionSession
├── aion_web.py                  # Web server (FastAPI + SSE)
├── aion_cli.py                  # CLI mode
├── aion_launcher.py             # Entry point (aion command)
├── onboarding.py                # Setup wizard (aion --setup)
├── plugin_loader.py             # Plugin loading + router registration
├── static/index.html            # Web UI (Vanilla JS, no build step)
├── Dockerfile                   # Docker image
├── docker-compose.yml           # Docker Compose
├── plugins/
│   ├── core_tools/              # continue_work, read_self_doc, system_info, memory_record
│   ├── shell_tools/             # shell_exec, winget_install, install_package
│   ├── web_tools/               # web_search, web_fetch
│   ├── file_tools/              # file_read, file_write (builtins in aion.py)
│   ├── scheduler/               # Cron scheduler (time + interval)
│   ├── telegram_bot/            # Telegram: text + images + voice
│   ├── discord_bot/             # Discord: DMs + @mentions + /ask + voice
│   ├── slack_bot/               # Slack: Socket Mode, DMs + mentions
│   ├── alexa_plugin/            # Amazon Alexa Skill
│   ├── playwright_browser/      # Browser automation (8 tools)
│   ├── multi_agent/             # Sub-agent delegation (4 tools)
│   ├── claude_cli_provider/     # Claude subscription via CLI (ask_claude, login, routing)
│   ├── gemini_provider/         # Google Gemini
│   ├── anthropic_provider/      # Anthropic Claude (API key)
│   ├── deepseek_provider/       # DeepSeek
│   ├── grok_provider/           # xAI Grok
│   ├── ollama_provider/         # Local Ollama
│   ├── memory_plugin/           # Conversation history (JSONL, channel-aware)
│   ├── audio_pipeline/          # Transcription (ffmpeg+Vosk) + TTS (edge-tts/pyttsx3)
│   ├── heartbeat/               # Keep-alive + autonomous todo processing
│   ├── updater/                 # Daily GitHub release check + channel notifications
│   ├── restart_tool/            # Process restart with user confirmation
│   ├── todo_tools/              # Task management
│   ├── smart_patch/             # Fuzzy code patching
│   ├── image_search/            # Image search (Openverse + Bing)
│   ├── docx_tool/               # Create Word documents
│   └── moltbook/                # Social platform moltbook.com
├── prompts/
│   └── rules.md                 # System prompt / behavioral rules
├── character.md                 # AION's personality — evolves automatically over time
├── AION_SELF.md                 # Technical self-documentation — AION reads this on demand
├── CHANGELOG.md                 # What changed (AION reads this)
├── aion_memory.json             # Persistent memory (max. 300 entries)
├── conversation_history.jsonl   # Full conversation history (channel-aware)
├── config.json                  # Active model + settings
└── .env                         # API keys (git-ignored)
```

---

## 📝 Living Files

`character.md` and `AION_SELF.md` ship with sensible defaults and **grow over time** — AION updates its own personality and self-documentation automatically as it learns. When you first clone the repo, these are clean starting points. Do not delete them; they are part of AION's identity and technical memory.

---

## 🔒 Security Notes

- `.env` is in `.gitignore` — **never commit API keys**
- Web server binds to `127.0.0.1` by default (LAN: `AION_HOST=0.0.0.0`)
- `shell_exec` runs arbitrary shell commands — **use only on trusted systems**
- Code editing tools show a diff and ask for confirmation before applying changes
- Scheduler tasks run with full AION permissions — phrase tasks carefully
- Claude CLI login opens your default browser on the local machine only

---

## 🔄 Updates

AION checks for new releases automatically once per day and notifies you across all active channels.

```bash
# Update to the latest version
aion update
```

This runs `git pull` + `pip install -e .` in one step — no manual commands needed.

**Automatic notifications:** When a new version is available, AION sends a message to every configured channel (Telegram, Discord, Slack) and shows a banner in the Web UI.

**Setup** — add to `.env`:
```env
AION_GITHUB_REPO=xynstr/aion
```

**Manual check** — ask AION in chat:
```
"check_for_updates"
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|---------|
| Menu shows raw codes like `[2m>` | Update to latest — ANSI/VT100 is now enabled automatically on Windows |
| `aion --setup` does nothing | Run `pip install -r requirements.txt && pip install -e .` first, then retry |
| Onboarding wizard doesn't appear | Delete `aion_onboarding_complete.flag` and run `aion --setup` |
| `No module named 'google'` | `pip install google-genai` (or re-run `pip install -r requirements.txt`) |
| Gemini key shown as "set" after fresh install | Stale `.env` file — delete it and run `aion --setup` again |
| Plugin not loading | Check `aion_events.log` — usually a missing `pip install <package>` |
| Provider not responding | Verify the API key in `.env` matches the provider's variable name |
| Providers listed multiple times in Web UI | Restart AION — fixed automatically with the dedup in `register_provider()` |
| "Ja" confirmation button does nothing | Fixed in current version — update to latest and restart |
| AION executes actions without confirmation | Fixed in current version — update to latest and restart |
| Discord/Slack bot silent | Check token in `.env` + required permissions/intents in developer portal |
| Playwright not found | `python -m playwright install chromium` |
| ffmpeg not in PATH | AION auto-searches WinGet install paths; or add ffmpeg to PATH manually |
| Port already in use | Set `AION_PORT=7001` in `.env` |
| Claude CLI 404 after update | New web endpoints require a full AION restart (not just plugin reload) |
| Voice messages not working | Install ffmpeg + set `tts_engine=edge` in config |

Log files: `aion_events.log`, `aion_start.log`

---

## 📋 Available Models

| Provider | Models | Access |
|----------|--------|--------|
| **Google Gemini** | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.0-flash` | API key (free tier) or Google OAuth |
| **OpenAI** | `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `o3`, `o4-mini` | API key |
| **Anthropic** | `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001` | API key or Claude.ai subscription |
| **DeepSeek** | `deepseek-chat`, `deepseek-reasoner` | API key |
| **Grok (xAI)** | `grok-3`, `grok-3-mini`, `grok-2` | API key |
| **Ollama** | any local model (`ollama/llama3.2`, `ollama/qwen2.5`, …) | Free, local |

Switch model: Web UI dropdown, `POST /api/model`, or just say: *"Switch to claude-opus-4-6"*

---

## 🧠 How the LLM Loop Works

```
User message (Web UI / CLI / Telegram / Discord / Slack / Scheduler)
      ↓
System prompt: character.md + plugin descriptions + memory
      ↓
LLM call
      ↓
  ┌── Tool calls → dispatch → results → continue (max 50×)
  │
  └── Text response:
        ├─ Completion check: "Did AION announce something without doing it?"
        │     YES → [System] inject → next iteration
        └─ Task enforcer: "Is the task truly complete?"
              NO  → [System] inject → next iteration
              YES → done event → response sent to user
      ↓
Response: text + images + audio rendered in Web UI / forwarded to channel
      ↓
Auto-memory: every 5 conversations → pattern recognition → character.md update
```

---

<div align="center">

Made with Python · Powered by your choice of AI

*AION is designed to be fully transparent — its entire codebase, prompts, and memory are readable and editable at any time.*

</div>
