# AION — Autonomous Intelligent Operations Node

An autonomous AI agent for Windows. Runs as a Python process, communicates via the Google Gemini or OpenAI API, executes tools, learns, and can modify itself.

---

## Features

- **Autonomous operation** — up to 50 tool iterations without waiting for the user, with automatic completion check + task enforcer
  - **Completion Check** — after tool calls: "did AION announce an action but not carry it out?"
  - **Task Enforcer** — after tool calls: "is the task truly complete, or are steps still missing?" → force-continues if incomplete
- **Scheduled tasks** — scheduler with fixed times (`06:00`) and intervals (`every 5m`) — runs fully autonomously
- **Self-modification** — reads, patches, and overwrites its own code; creates new plugins
- **Web UI** — live stream of responses, thoughts, and tool calls; persistent sidebar navigation (Chat / Prompts / Plugins / Memory / System)
- **CLI mode** — fully without browser/server: `start_cli.bat` or `python aion_cli.py`; color terminal output with tool/thought display
- **Telegram** — bidirectional: text, images, and voice messages (OGG → Vosk transcription, TTS reply)
  - Channel-isolated history: only Telegram chats load Telegram history (no web context bleed)
  - `memory_read_web_history` tool: load Web UI history on request and carry over context
- **Memory** — persistent JSON memory + conversation history (JSONL) with channel filtering
- **Personality** — `character.md` evolves through conversations; LLM analysis with pattern recognition every 5 conversations
- **Multi-provider** — Universal provider plugin architecture: Gemini, OpenAI, Anthropic Claude, DeepSeek, Grok, Ollama (local) — any OpenAI-compatible API works via a simple plugin
  - New providers = one plugin file, no core changes needed
  - `/api/providers` endpoint returns all registered providers with their models
- **Plugin system** — `plugins/<name>/<name>.py` is loaded automatically; READMEs are injected as plugin overviews
  - **create_plugin tool** enforces correct subdirectory structure (even when AION passes incorrect paths)
  - Auto-generated README.md in every new plugin
- **Audio pipeline** — any audio format → transcription (ffmpeg + Vosk, offline) + TTS (edge-tts neural / pyttsx3/SAPI5, offline)
  - edge-tts: Microsoft Neural TTS, free, online, no API key (`de-DE-KatjaNeural` default)
- **Moltbook** — social presence: read feed, create posts, comment

---

## Requirements

- Python 3.10+
- Windows (for `shell_exec`, `winget_install`)
- At least one API key: Gemini, OpenAI, Anthropic, DeepSeek, or Grok — or a local Ollama server

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file in the project directory:

```env
GEMINI_API_KEY=AIza...              # Google Gemini
OPENAI_API_KEY=sk-...               # OpenAI (default fallback)
ANTHROPIC_API_KEY=sk-ant-...        # Anthropic Claude
DEEPSEEK_API_KEY=sk-...             # DeepSeek
XAI_API_KEY=xai-...                 # xAI Grok
# Ollama: no key needed — local server at localhost:11434
TELEGRAM_BOT_TOKEN=1234...:AAE...   # optional
TELEGRAM_CHAT_ID=123456789          # optional
AION_MODEL=gemini-2.5-flash         # optional, default: gpt-4.1
AION_PORT=7000                      # optional, default: 7000
```

The active model is stored in `config.json` and restored on the next start.

**Tip:** Run `python onboarding.py` for a guided setup that asks about all providers and their models.

---

## Starting / Stopping

```bash
start.bat        # Starts web server + opens browser (kills old instances)
start_cli.bat    # Starts interactive CLI mode (no browser needed)
stop.bat         # Stops all AION processes cleanly
restart.bat      # Stop + Start
status.bat       # Shows whether the server is running
```

Or manually:
```bash
python aion_web.py   # Web server (port 7000)
python aion_cli.py   # CLI mode (interactive terminal)
```

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
│ ⊞ System │         as inline accordions (centered)            │
│          │                                                     │
│          ├─────────────────────────────────────────────────────┤
│          │   [Input…]                                [▶]       │
└──────────┴─────────────────────────────────────────────────────┘
```

**Sidebar** (172px, always visible — no toggle):
- **💬 Chat** — main chat; thoughts + tool calls inline as expandable accordions
- **📝 Prompts** — edit `rules.md`, `character.md`, `AION_SELF.md` directly in the browser (full width)
- **🔌 Plugins** — all plugins with tools + status (✓/✗) + reload
- **🧠 Memory** — search memory, color-coded (green/red), delete entries
- **⊞ System** — statistics, switch model, paths, actions

## CLI Mode

```
> start_cli.bat

  ╔══════════════════════════════════════╗
  ║  AION  —  CLI Mode                   ║
  ╚══════════════════════════════════════╝

  Initializing AION… ✓
  Model: gemini-2.5-flash  |  Tools: 32

You  › list the files in the project directory
  ⚙  shell_exec({'command': 'dir /b'})  → ✓ aion.py aion_web.py aion_cli.py ...
AION › Here are the files in the directory: ...

You  › exit
  Session ended. Goodbye! 👋
```

- Thoughts appear as `💭 …` in purple
- Tool calls as `⚙ tool(args) → ✓/✗ result` in yellow/gray
- Responses as `AION › …` live-streamed in cyan
- Internal commands: `/help`, `/clear`, `/model`

---

## Scheduled Tasks (Scheduler)

AION can execute tasks at fixed times **or at intervals** autonomously:

```
"Schedule daily at 06:00: Read my emails, extract appointments and add them to the calendar."
"Schedule on weekdays at 08:00: Send me a short daily summary via Telegram."
"Send me a Telegram message every 5 minutes with the current status."
"Remind me every hour to drink water."
```

**Interval syntax:** `"5m"`, `"30s"`, `"1h"`, `"2h30m"`, `"every 10 minutes"`

Manage by voice or directly:
- `schedule_list` — show all tasks
- `schedule_remove` — delete a task
- `schedule_toggle` — enable/disable a task

---

## Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather) → token
2. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
3. Start AION — Telegram polling starts automatically

AION will message you on its own when:
- A scheduler task completes
- You tell it `"Message me via Telegram when X is done"`

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

**Important:** `def fn(param: str = "", **_)` — no `input: dict` parameters!

### Plugin with Custom Web Endpoints

Plugins can also provide their own HTTP routes — without touching `aion_web.py`:

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/myplugin/status")
async def status():
    return {"ok": True}

def register(api):
    api.register_tool(...)                              # LLM tool as usual
    api.register_router(router, tags=["myplugin"])     # custom HTTP routes
```

New plugins are loaded immediately — no restart needed (except for changes to `aion.py`).
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
| GET | `/api/memory` | Memory entries (`?search=`, `?limit=`, `?offset=`) — paginated |
| DELETE | `/api/memory` | Clear memory |
| GET | `/api/providers` | All registered LLM providers + active model |
| GET | `/api/config` | Configuration + statistics |
| GET | `/api/prompt/{name}` | Read prompt (`rules`, `character`, `self`) |
| POST | `/api/prompt/{name}` | Save prompt |

---

## File System

```
AION/
├── aion.py                      # Core logic: memory, tools, LLM loop, AionSession
├── aion_web.py                  # Web server (FastAPI + SSE), port 7000
├── aion_cli.py                  # CLI mode: interactive terminal without browser
├── plugin_loader.py             # Loads plugins + register_router support
├── static/index.html            # Web UI (Vanilla JS, persistent sidebar)
├── plugins/
│   ├── core_tools/              # continue_work, read_self_doc, system_info, memory_record
│   ├── reflection/              # reflect (inner monologue → thoughts.md)
│   ├── character_manager/       # update_character (update character.md)
│   ├── shell_tools/             # shell_exec, winget_install, install_package
│   ├── web_tools/               # web_search, web_fetch
│   ├── pid_tool/                # get_own_pid
│   ├── restart_tool/            # restart_with_approval
│   ├── audio_pipeline/          # Any audio format → text (ffmpeg+Vosk) + TTS (pyttsx3)
│   ├── audio_transcriber/       # WAV → text via Vosk (base transcription)
│   ├── scheduler/               # Cron scheduler (schedule_add/list/remove/toggle)
│   ├── moltbook/                # Social platform moltbook.com (feed, posts, comments)
│   ├── telegram_bot/            # Telegram: text + images + voice messages
│   ├── gemini_provider/         # Google Gemini (prefix "gemini")
│   ├── anthropic_provider/      # Anthropic Claude (prefix "claude")
│   ├── deepseek_provider/       # DeepSeek (prefix "deepseek")
│   ├── grok_provider/           # xAI Grok (prefix "grok")
│   ├── ollama_provider/         # Local Ollama (prefix "ollama/")
│   ├── memory_plugin/           # Conversation history (JSONL)
│   ├── todo_tools/              # Task management
│   ├── smart_patch/             # Fuzzy code patching
│   ├── image_search/            # Image search (Openverse + Bing)
│   ├── docx_tool/               # Create Word documents
│   └── heartbeat/               # Keep-alive + autonomous todo processing (every 30min)
├── character.md                 # Personality (self-updating via update_character)
├── AION_SELF.md                 # Technical self-documentation for AION
├── aion_memory.json             # Persistent memory (max. 300 entries)
├── thoughts.md                  # Recorded thoughts
├── .env                         # API keys (not in Git)
├── config.json                  # Active model + conversation counter
├── start.bat                    # Starts web server + browser
├── start_cli.bat                # Starts CLI mode (no browser)
├── stop.bat                     # Stops all AION processes
├── restart.bat                  # Restart
└── status.bat                   # Check server status
```

---

## Available Models

| Provider | Model | Notes |
|----------|-------|-------|
| Google Gemini | `gemini-2.5-pro` | ★ Best quality |
| Google Gemini | `gemini-2.5-flash` | Fast & affordable |
| Google Gemini | `gemini-2.5-flash-lite` | Lightweight |
| Google Gemini | `gemini-2.0-flash` | Stable |
| OpenAI | `gpt-4.1` | OpenAI flagship |
| OpenAI | `gpt-4.1-mini` | Affordable |
| OpenAI | `gpt-4o` | Multimodal |
| OpenAI | `o3` | Reasoning |
| OpenAI | `o4-mini` | Fast reasoning |
| Anthropic | `claude-opus-4-6` | ★ Most capable Claude |
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

## Provider Plugins

AION uses a registry-based provider system. Each provider is a plugin in `plugins/<name>/`.
Add any provider by creating a plugin that calls `register_provider(prefix, build_fn, label, models)`.

| Plugin | `.env` Key | Prefix |
|--------|------------|--------|
| `gemini_provider` | `GEMINI_API_KEY` | `gemini` |
| `anthropic_provider` | `ANTHROPIC_API_KEY` | `claude` |
| `deepseek_provider` | `DEEPSEEK_API_KEY` | `deepseek` |
| `grok_provider` | `XAI_API_KEY` | `grok` |
| `ollama_provider` | _(none)_ | `ollama/` |
| _(fallback)_ | `OPENAI_API_KEY` | _(any)_ |

Providers with missing API keys are skipped silently at startup.

---

## Security Notice

- `.env` is in `.gitignore` — never commit API keys
- `shell_exec` runs arbitrary Windows commands — use only on trusted systems
- `self_modify_code` / `self_patch_code` — AION asks for confirmation before making code changes
- Scheduler tasks run with full AION permissions — formulate tasks carefully
