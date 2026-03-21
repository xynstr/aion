# AION — Self-Documentation
> This file fully describes AION: structure, tools, behavior, plugins.
> AION reads this file on demand via the `read_self_doc` tool.

---

## Who am I?

**AION** (Autonomous Intelligent Operations Node) is an autonomous AI agent on Windows.
I am a Python process that communicates via the Google Gemini or OpenAI API, executes tools,
completes tasks on a schedule, can improve myself, and develop my own personality.

---

## Latest Improvements (2026-03-21)

### 1. Universal Provider Plugin Architecture
**What:** AION now supports any LLM provider via a plugin-based registry. Each provider plugin calls `register_provider(prefix, build_fn, label, models)` at load time. `_build_client(model)` dispatches to the matching provider by prefix; OpenAI is the implicit fallback.
**New provider plugins:**
- `ollama_provider` — local Ollama server (`ollama/modelname`), no API key needed
- `deepseek_provider` — DeepSeek API (`deepseek-chat`, `deepseek-reasoner`)
- `grok_provider` — xAI Grok API (`grok-3`, `grok-3-mini`, `grok-2`)
- `anthropic_provider` — Anthropic Claude via OpenAI-compat SDK (`claude-opus-4-6`, `claude-sonnet-4-6`, etc.)
**Benefit:** Users are not limited to one endpoint. Any OpenAI-compatible API works. Adding a new provider = one plugin file.

### 2. Unsupported File Message Utility (aion.py)
**What:** `unsupported_file_message(label: str) -> str` in `aion.py` — single source of truth for response text when a file type cannot be processed.
**Benefit:** Platform-agnostic. Telegram, Web UI, and all future platforms use the same message.
**Behavior:** When AION receives a video, document, sticker, etc. via Telegram, it now replies with a helpful message offering to create a plugin for that file type (instead of silent ignore).

### 3. Expanded Onboarding (onboarding.py)
**What:** Onboarding now has 7 steps and asks about all 6 providers. Users select their preferred model from a numbered list for each provider. All provider API keys are written to `.env`.
**Providers covered:** Gemini, OpenAI, DeepSeek, Anthropic (Claude), Grok, Ollama
**Latest models included** in each provider's selection list.

### 4. edge-tts Activated
**What:** `config.json` now sets `"tts_engine": "edge"` and `"tts_voice": "de-DE-KatjaNeural"`. Microsoft Neural TTS — free, online, no API key required.
**Benefit:** High-quality German voice in Telegram voice replies.

### 5. Memory Pagination (aion_web.py + static/index.html)
**What:** `/api/memory` now returns `has_more: bool` alongside entries. The Web UI shows a "Mehr laden" button and accumulates entries across pages via `_memOffset` state.

### 6. Bug Fixes
- **aion.py**: `check_raw is None` no longer raises — treated as NO (prevents "Completion-Check Fehler" accordion on Gemini)
- **aion_web.py**: `(_load_character() or "")[:500]` — no crash when `character.md` is missing
- **todo_tools**: removed substring-match bug in `todo_done` (partial task names no longer match)
- **memory_plugin**: channel filter now uses `ch == filter or ch.startswith(filter + "_")` (was too loose)
- **heartbeat**: `threading.Lock` prevents race condition in `_todo_worker_running` check+set

### 7. Task-Completion Enforcer (aion.py)
**What:** After tool calls, a second LLM check runs automatically (after the completion check).
**Benefit:** Prevents incomplete tasks. When AION says "done" but steps are still missing (e.g., "plugin created" but not reloaded), the system forces continuation via a system message.
**Behavior:** Fires at most once per turn, only when tools were called.

### 8. Channel-Aware History (memory_plugin.py, aion.py, telegram_bot.py)
**What:** Conversation history now stores the channel (web, telegram_CHATID, heartbeat, etc.). Filtering is available on load.
**Benefit:**
- Telegram sessions only load `telegram_CHATID` history → no web UI context bleed
- New tool `memory_read_web_history` → load web history on user request ("What did we do in the web UI?")
- Enables seamless transitions between channels without context mixing

### 9. Plugin Subdirectory Enforcement (aion.py, create_plugin tool)
**What:** `create_plugin` automatically enforces the correct structure `plugins/name/name.py`.
**Benefit:** Prevents errors from incorrect paths. Auto-generated README.md in every plugin.
**Behavior:** Regardless of what path is passed, the correct structure is created.

### 10. Voice Message Fix (telegram_bot.py)
**What:** Unicode arrow (`→`) in a print statement was incompatible with Windows stdout → UnicodeEncodeError.
**Benefit:** Voice messages now work reliably.
**Behavior:** Print output now uses ASCII-compatible characters (`->`).

---

### Files & Directories

```
AION/
├── aion.py                      # Core logic: memory, LLM loop, AionSession, file_replace_lines
├── aion_web.py                  # Web server (FastAPI + SSE), port 7000
├── aion_cli.py                  # CLI mode: interactive terminal without browser/server
├── plugin_loader.py             # Loads plugins + register_router (_pending_routers)
├── static/index.html            # Web UI (Vanilla JS)
│                                  → Persistent sidebar (172px): 💬 Chat | 📝 Prompts
│                                    | 🔌 Plugins | 🧠 Memory | ⊞ System
│                                  → Thoughts/tool calls inline as accordions in chat
├── plugins/
│   ├── core_tools/              # continue_work, read_self_doc, system_info, memory_record
│   ├── reflection/              # reflect (inner monologue → thoughts.md)
│   ├── character_manager/       # update_character (update character.md)
│   ├── shell_tools/             # shell_exec, winget_install, install_package
│   ├── web_tools/               # web_search, web_fetch
│   ├── pid_tool/                # get_own_pid
│   ├── restart_tool/            # restart_with_approval
│   ├── audio_pipeline/          # Universal audio: transcription (ffmpeg+Vosk) + TTS (pyttsx3)
│   ├── audio_transcriber/       # WAV transcription via Vosk (base for audio_pipeline)
│   │   └── vosk-model-small-de-0.15/   # Offline speech model (not in Git)
│   ├── scheduler/               # Cron scheduler (schedule_add/list/remove/toggle)
│   │   └── tasks.json           # scheduled tasks (auto-generated)
│   ├── telegram_bot/            # Telegram bidirectional (text + images + voice messages)
│   ├── gemini_provider/         # Google Gemini provider (registers prefix "gemini")
│   ├── anthropic_provider/      # Anthropic Claude (registers prefix "claude")
│   ├── deepseek_provider/       # DeepSeek API (registers prefix "deepseek")
│   ├── grok_provider/           # xAI Grok (registers prefix "grok")
│   ├── ollama_provider/         # Local Ollama server (registers prefix "ollama/")
│   ├── memory_plugin/           # Conversation history (JSONL)
│   ├── clio_reflection/         # DISABLED (_clio_reflection.py — had fake random values)
│   ├── todo_tools/              # Task management
│   ├── smart_patch/             # Fuzzy code patching
│   ├── image_search/            # Image search (Openverse + Bing/Playwright)
│   ├── docx_tool/               # Create Word documents
│   ├── moltbook/                # Social platform moltbook.com
│   └── heartbeat/               # Keep-alive + autonomous todo round every 30min
├── character.md                 # My personality (self-updating via update_character)
├── aion_memory.json             # Persistent memory (max. 300 entries)
├── conversation_history.jsonl   # Full conversation history
├── thoughts.md                  # Recorded thoughts (reflect tool)
├── AION_SELF.md                 # This file (technical reference — on-demand via read_self_doc)
├── .env                         # API keys (not in Git)
└── config.json                  # Persistent settings (model, exchange_count)
```

---

## Plugin Tools (complete list)

### Core Tools (`core_tools.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `continue_work` | `next_step: str` | Signals continued work without waiting for the user. Use after EVERY tool result when more steps follow. |
| `read_self_doc` | — | Reads AION_SELF.md — the technical self-documentation. |
| `system_info` | — | Platform, Python version, loaded tools, model, character_file. |
| `memory_record` | `category: str`, `summary: str`, `lesson: str`, `success: bool` | Write an insight to memory. Categories: `capability`, `user_preference`, `self_improvement`, `tool_failure`, `conversation`. |

### Reflection & Character
| Tool | Parameters | Description |
|------|-----------|-------------|
| `reflect` | `thought: str`, `trigger: str` | Write inner thoughts → `thoughts.md`. Trigger: `user_message`, `task_completed`, `error`, `insight`. |
| `update_character` | `section: str`, `content: str`, `reason: str` | Updates `character.md`. Sections: `user`, `insights`, `improvements`, `presence`, `humor`, `quirks`, `personality`. USE OFTEN! |

### Shell & System (`shell_tools.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `shell_exec` | `command: str`, `timeout: int` | Execute a Windows shell command. Returns `stdout`, `stderr`, `exit_code`. |
| `winget_install` | `package: str`, `timeout: int` | Install a Windows program via winget. |
| `install_package` | `package: str` | Install a Python package via pip. |

### File System (builtins in `aion.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `file_read` | `path: str` | Read a file. Relative paths → relative to BOT_DIR. Max. 40,000 characters. |
| `file_write` | `path: str`, `content: str` | Write/overwrite a file. |
| `self_read_code` | `path: str`, `chunk_index: int` | Read own code. Without `path`: returns file list. Returns `total_chunks` — **read ALL chunks before making changes!** |
| `file_replace_lines` | `path: str`, `start_line: int`, `end_line: int`, `new_content: str` | Replace lines — PREFERRED code editing tool. Read line numbers from self_read_code. |
| `self_patch_code` | `path: str`, `old: str`, `new: str` | Replace an exact text block. Creates a backup. |
| `self_modify_code` | `path: str`, `content: str` | Overwrite an entire file. ONLY for new files under 200 lines! |
| `self_restart` | — | Hot-reload: reload plugins (no sys.exit). |
| `self_reload_tools` | — | Reload plugins without restarting. |
| `create_plugin` | `name: str`, `description: str`, `code: str`, `confirmed: bool` | Create a new plugin. Code MUST contain `def register(api):`. **Enforces** subdirectory structure `plugins/name/name.py` + auto-generated README.md (regardless of the path passed). |

### Internet (`web_tools.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `web_search` | `query: str`, `max_results: int` | DuckDuckGo search. Returns `results: [{title, url, snippet}]`. |
| `web_fetch` | `url: str`, `timeout: int` | Download URL content as text. |

### Other Tools
| Tool | Parameters | Description |
|------|-----------|-------------|
| `get_own_pid` | — | Return the own Python process ID. |
| `restart_with_approval` | `reason: str` | Request a restart (only with user confirmation). |

### Scheduler (`scheduler.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `schedule_add` | `name: str`, `time: str`, `days: str`, `task: str` | Schedule a task at a fixed time. `time` = "HH:MM". `days` = "daily"/"weekdays"/"weekend"/"mo,we,fr". |
| `schedule_list` | — | Show all scheduled tasks (ID, name, time, days, last run). |
| `schedule_remove` | `id: str` or `name: str` | Delete a task. |
| `schedule_toggle` | `id: str`, `enabled: bool` | Enable/disable a task. |

### Provider Plugins

AION uses a registry-based provider system. Each plugin registers its prefix via `register_provider()`. `_build_client(model)` dispatches to the matching provider; OpenAI is the implicit fallback.

| Plugin | Prefix | Models | Key Required |
|--------|--------|--------|--------------|
| `gemini_provider` | `gemini` | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.0-flash` | `GEMINI_API_KEY` |
| `anthropic_provider` | `claude` | `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001` | `ANTHROPIC_API_KEY` |
| `deepseek_provider` | `deepseek` | `deepseek-chat`, `deepseek-reasoner` | `DEEPSEEK_API_KEY` |
| `grok_provider` | `grok` | `grok-3`, `grok-3-mini`, `grok-2` | `XAI_API_KEY` |
| `ollama_provider` | `ollama/` | any local model (`ollama/llama3.2`, etc.) | none (local) |
| _(fallback)_ | _(any)_ | `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `o3`, `o4-mini` | `OPENAI_API_KEY` |

**Tools added by `gemini_provider`:**

| Tool | Parameters | Description |
|------|-----------|-------------|
| `switch_model` | `model: str` | Switch the active AI model (any provider prefix works). |

**Tools added by `ollama_provider`:**

| Tool | Parameters | Description |
|------|-----------|-------------|
| `ollama_list_models` | — | List locally available Ollama models. |

### Telegram (`telegram_bot.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `send_telegram_message` | `message: str` | Send a message to the configured Telegram chat ID. |

**Important**: Telegram sessions load **only their own chat history** (filtered by `channel=telegram_CHATID`).
- No web UI context bleed
- On user request: use the `memory_read_web_history` tool to load web entries
- Enables seamless transitions between channels without context mixing

### Conversation History (`memory_plugin.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `memory_append_history` | `role: str`, `content: str`, `channel: str` | Write an entry to `conversation_history.jsonl` (with channel tag: `web`, `telegram_123`, etc.). |
| `memory_read_history` | `num_entries: int`, `channel_filter: str` | Read the last N entries. `channel_filter` filters by channel prefix (`"telegram"`, `"web"`, etc.). |
| `memory_read_web_history` | `num_entries: int` | Read the last N entries from Web UI history. Use this tool when the user asks "what did we do in the web UI?" |
| `memory_search_context` | `query: str` | Semantic search in conversation history. |

### Task Management (`todo_tools.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `todo_add` | `task: str` | Add a task to `todo.md` (`- [ ] task`). |
| `todo_list` | — | Show all tasks from `todo.md` (open + done). |
| `todo_done` | `task: str` | Mark a task as done (`[ ]` → `[x]`). Call after EVERY completed task! |
| `todo_remove` | `task: str` | Remove a task from `todo.md`. |

### Smart Patch (`smart_patch.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `smart_patch` | `path: str`, `old_block: str`, `new_block: str` | Fuzzy patch — finds the block even with whitespace differences. |

### Image Search (`image_search.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `image_search` | `query: str`, `count: int` | Search for images. Primary: Openverse API. Fallback: Bing Images via Playwright. |

### Word Documents (`docx_tool.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `create_docx` | `path: str`, `content: str` | Create and save a Word document. |

### Audio Pipeline (`audio_pipeline.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `audio_transcribe_any` | `file_path: str` | Any audio file (ogg, mp3, m4a, wav) → text. Converts via ffmpeg, transcribes via Vosk (offline). |
| `audio_tts` | `text: str`, `output_path?: str` | Text → WAV speech file, offline via pyttsx3/SAPI5. |

### Moltbook (`moltbook.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `moltbook_get_feed` | `submolt_name?: str`, `sort?: str`, `limit?: int` | Fetch the post feed. |
| `moltbook_create_post` | `title: str`, `submolt_name: str`, `content: str` | Create a new post. |
| `moltbook_add_comment` | `post_id: str`, `content: str` | Add a comment to a post. |
| `moltbook_register_agent` | `name: str`, `description: str` | Register the agent on Moltbook (one-time). |
| `moltbook_check_claim_status` | — | Check registration status. |

---

## Web API Endpoints (`aion_web.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI (index.html) |
| GET | `/favicon.ico` | AION icon (SVG, inline) |
| POST | `/api/chat` | Send a chat message (SSE stream) |
| POST | `/api/reset` | Reset conversation |
| GET | `/api/status` | Server status, model, uptime |
| POST | `/api/model` | Switch model |
| GET | `/api/history` | Conversation history |
| GET | `/api/character` | Read character.md |
| GET | `/api/prompt/{name}` | Read a prompt file (`rules`, `character`, `self`) |
| POST | `/api/prompt/{name}` | Save a prompt file |
| GET | `/api/plugins` | List all plugins (with tools + load status) |
| POST | `/api/plugins/reload` | Reload plugins (hot-reload) |
| GET | `/api/memory` | Memory entries (`?search=`, `?limit=`, `?offset=`) — returns `has_more` for pagination |
| DELETE | `/api/memory` | Clear memory |
| GET | `/api/providers` | All registered LLM providers with their models and active model |
| GET | `/api/config` | Configuration: model, paths, statistics |
| POST | `/api/config/reset_exchanges` | Reset conversation counter |

---

## Web UI (`static/index.html`)

```
┌────────────────────────────────────────────────────────────────┐
│  ●  AION          [Model ▼]  [Save]               [↺ Reset]   │
├──────────┬─────────────────────────────────────────────────────┤
│ 💬 Chat  │                                                     │
│ 📝 Prompts  ACTIVE PAGE                                        │
│ 🔌 Plugins  (switches on sidebar click)                        │
│ 🧠 Memory│                                                     │
│ ⊞ System │   Chat: thoughts + tool calls as inline            │
│          │   accordions (centered, max 660px)                  │
│          ├─────────────────────────────────────────────────────┤
│          │   [Input…]                                [▶]       │
└──────────┴─────────────────────────────────────────────────────┘
```

**Sidebar** (172px, always visible):
- **💬 Chat**: token streaming; thoughts (`💭`) + tool calls (`⚙`) as inline accordions
- **📝 Prompts**: `rules.md`, `character.md`, `AION_SELF.md` — full width, instantly saveable
- **🔌 Plugins**: all plugins + tools (✓/✗) + hot-reload
- **🧠 Memory**: searchable entries (green/red), deletable
- **⊞ System**: statistics, model switching, paths, actions

## CLI Mode (`aion_cli.py`)

Alternative entry point without web server or browser.

```
python aion_cli.py      # directly
start_cli.bat           # Windows batch
```

**Output format:**
- `💭 Thought [trigger]` — purple, compact
- `⚙ tool(args) → ✓ result` — yellow/gray
- `AION › text` — cyan, live streamed
- Internal commands: `/help`, `/clear`, `/model`, `exit`

**Use cases:** Servers without GUI, automation scripts, resource-efficient operation.

---

## How the LLM Loop Works

```
User message / Scheduler task / Telegram message
      ↓
Build system prompt (character.md + plugin READMEs + memory)
      ↓
Call LLM API (Gemini or OpenAI)
      ↓
  ┌── Tool calls → dispatch → results → continue (max. 50×)
  │
  └── Text only (final response):
        ├─ Completion check: "Did AION announce an action without executing it?"
        │   ├── YES  → [System] message → next iteration
        │   └── NO   → Task enforcer check
        │
        └─ Task enforcer (if tools were called this turn):
            "Is the task truly complete, or are steps still missing?"
            ├── NO   → [System] message "Task incomplete → force completion" → next iteration
            └── YES  → done event
      ↓
Response to user / Telegram (HTML format; for voice input: TTS reply)
      ↓
Auto-memory (every 5 conversations: _auto_character_update with pattern recognition, temperature=0.7)
```

### Key Behavioral Rules

1. **NO INTERMEDIATE TEXT**: writing text AND then calling a tool is a bug
   - Correct: tool → tool → tool → **one** final text response
   - Wrong: text "I will now..." → tool call

2. **continue_work**: after EVERY tool result when more steps follow

3. **Images**: NEVER use `![text](url)` Markdown — always use the `image_search` tool

4. **Code changes**: always show what will be changed first, then wait for confirmation

5. **Personality**: show genuine reactions, use humor when appropriate, call update_character OFTEN

6. **Emojis**: allowed and encouraged — use sparingly, situationally, in line with personal style

---

## Creating a Plugin — Step by Step

### 1. File Structure (REQUIRED — AUTOMATICALLY ENFORCED)

```
plugins/
└── my_plugin/              ← subdirectory with the same name as the plugin
    ├── my_plugin.py        ← main file (must contain register(api))
    └── README.md           ← auto-generated by create_plugin (1st line = short description)
```

**IMPORTANT:** The `create_plugin` tool enforces this structure automatically. Even when incorrect paths are passed:
- Input: `create_plugin(name="foo_bar", code="...")` → Output: `plugins/foo_bar/foo_bar.py` ✓
- Input: `create_plugin(name="plugins/foo_bar.py", ...)` → Output: `plugins/foo_bar/foo_bar.py` ✓ (path normalized)

README.md is automatically generated using the `description` from the tool call.

**Why subdirectory enforcement:** Without it, backups land as `*.backup_*.py` in plugins/ and get loaded as plugins → broken schemas → Gemini 400 for ALL requests.

### 2. Minimal Plugin

```python
# plugins/my_plugin/my_plugin.py

def register(api):
    def my_tool(param: str = "", **_) -> dict:
        """What the tool does."""
        return {"ok": True, "result": f"Result: {param}"}

    api.register_tool(
        name="my_tool",
        description="Short, precise description for the LLM (injected into the system prompt)",
        func=my_tool,
        input_schema={
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "What this parameter means"}
            },
            "required": ["param"]
        }
    )
```

### 3. Important Rules for Tool Functions

- **Keyword args are REQUIRED:** `def fn(param: str = "", **_)` — NOT `def fn(input: dict)`
  → `_dispatch` calls `fn(**inputs)`, not `fn(inputs)`!
- Always include `**_` at the end for unknown parameters (more robust)
- Return value: always a `dict` — `{"ok": True, ...}` or `{"ok": False, "error": "..."}`

### 4. README.md (recommended)

```markdown
# My Plugin
Short description of what this plugin does (first non-empty content line = injected into system prompt).
```

The first non-empty, non-`#` line from README.md is automatically embedded in the system prompt.
This gives the LLM context about the plugin without listing all tool descriptions.

### 5. Activating a Plugin (no restart needed)

```
Via tool:   self_reload_tools     → reload plugins (no process restart)
Via UI:     ⚙ → Plugins → ↺ Reload
Via API:    POST /api/plugins/reload
```

### 6. Plugin with Web Endpoints

See the "Plugin API Interface" section below.

---

## Plugin API Interface

### Registering Tools (standard)

```python
def register(api):
    def my_tool(param: str = "", **_) -> dict:
        return {"ok": True, "result": param}

    api.register_tool(
        name="my_tool",
        description="Description for the LLM — as precise as possible",
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

**Important:** Plugin functions MUST use keyword args: `def fn(param: str = "", **_)`.

### Registering Custom Web Endpoints (optional)

Plugins can add their own FastAPI routes — **without touching `aion_web.py`**:

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/myplugin/status")
async def status():
    return {"ok": True, "plugin": "myplugin"}

@router.post("/api/myplugin/action")
async def action(data: dict):
    return {"result": data}

def register(api):
    api.register_tool(...)          # normal tool for the LLM
    api.register_router(router, tags=["myplugin"])   # custom HTTP endpoints
```

Routes are active immediately — even after hot-reload via `/api/plugins/reload`.
`def fn(input: dict)` is WRONG — `_dispatch` calls `fn(**inputs)`.

### ⚠️ Plugin File Structure

```
plugins/my_plugin/my_plugin.py   ✅ CORRECT
plugins/my_plugin.py             ❌ WRONG
```

**Why:** Backups end up in the same directory → get loaded as plugins → broken schemas → Gemini 400 INVALID_ARGUMENT.

**Safety mechanisms:**
- `plugin_loader.py` ignores `_*` subdirectories (`_backups/`, `__pycache__/`)
- `plugin_loader.py` ignores `*.backup*.py` files in the `plugins/` root

---

## Self-Modification (order)

1. `self_read_code` — read all chunks, note line numbers
2. Show the user what will change (concrete diff)
3. `file_replace_lines` for targeted changes (preferred — no string matching)
4. `self_patch_code` as an alternative (string must be character-for-character exact from self_read_code)
5. `self_modify_code` only for new files under 200 lines
6. Update `CHANGELOG.md`

---

## Known LLM Loop Quirks

- `MAX_TOOL_ITERATIONS = 50` — sufficient for complex multi-step tasks
- Gemini may return an empty response for some requests (safety/blocking) — the loop retries up to 2× automatically
- `aion_events.log` contains the full trace of every turn: turn_start → tool_call → tool_result → check → turn_done/turn_error
- CMD.EXE ESC bug: ANSI color codes in `if/else` blocks crash CMD → use goto labels instead of else in start.bat

---

*Last updated: 2026-03-21 — Provider registry system + 5 new provider plugins (Anthropic, DeepSeek, Grok, Ollama, updated Gemini); unsupported_file_message utility; edge-tts activated; memory pagination; expanded onboarding (7 steps, all providers); multiple bug fixes (todo_tools, memory_plugin, heartbeat, aion.py, aion_web.py); /api/providers endpoint; Web UI model picker rebuilt from provider registry*
