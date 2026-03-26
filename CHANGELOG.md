# AION — Changelog

This document describes what has changed. AION reads this on startup to know what is new.
**Required:** Add an entry after each self-modification (code, plugin, config).

---

## 2026-03-26 — Personality 2.0 + Proactive AI + Desktop Automation + Self-Healing

### Evolving Personality 2.0
- **Mood Engine** (`plugins/mood_engine/`): 5-state mood system (curious/focused/playful/calm/reflective)
  computed from time-of-day, conversation topic keywords, and tool error signals
- Mood hint injected into every system prompt — influences AION's communication style dynamically
- **Relationship Depth**: 5 levels based on `exchange_count` — progressively richer collaboration style
- **Temporal Awareness**: morning/late-night context hint injected per call
- Tools: `mood_check`, `mood_set`

### Proactive Wake-on-Trigger
- **Proactive plugin** (`plugins/proactive/`): daily analysis at 08:30 weekdays
  reads conversation history + memory, finds unfinished tasks and open questions via LLM
- **Server-Push SSE** (`GET /api/events`): persistent browser connection with 30s heartbeat
- **Push Toast UI**: slide-in notification bottom-right with Accept/Dismiss buttons (auto-dismiss 30s)
- Tools: `proactive_check`, `proactive_clear`

### Desktop Automation
- **Desktop plugin** (`plugins/desktop/`): full-screen screenshot (base64 PNG), click, type,
  hotkey, scroll, mouse move — all via pyautogui
- Destructive actions require `confirmed=true` (approval pattern)
- Headless/server guard: auto-disabled when `$DISPLAY` unset on Linux
- Requires: `pip install pyautogui Pillow`

### Self-Healing Workflows
- `_dispatch()` checks `retry_policy` on plugin tools before executing
- `_dispatch_with_retry()`: exponential backoff, silent retries for transient errors
- `_classify_error()`: categorizes errors as network/resource/not_found/fatal
- Alternative tool suggestions appended after max retries exhausted
- `PluginAPI.register_tool()` accepts `retry_policy` dict

### Bug Fixes & Refactoring
- Removed dead `chat_turn()` function (replaced by `AionSession.stream()`)
- `run_aion_turn()` now uses per-channel `AionSession` registry (no more `_conversations` dict)
- `aion_web.py` delegates `_load_config`/`_save_config` to `config_store.py` (thread-safe)
- `shell_tools.py` fallback uses `MAX_MEMORY` from `aion` instead of hardcoded `300`

---

## 2026-03-26 — Agentic RAG Memory + MCP Support

### Agentic RAG Memory
- `AionMemory.get_context_semantic()` — async semantic search via Ollama `nomic-embed-text` embeddings
- Cosine similarity replaces keyword matching for memory retrieval
- Lazy embedding: up to 10 new entries embedded per turn (no startup delay)
- Vectors cached in `aion_memory_vectors.json` (gitignored, user-specific)
- Automatic fallback to keyword matching if Ollama is unavailable
- File: `aion.py` (AionMemory class, lines ~597–730)

### MCP Client Plugin
- New plugin `plugins/mcp_client/` — connects AION to any MCP server
- Server config via `mcp_servers.json` (committable, no secrets)
- Secrets injected from credentials vault (`vault_env` field in config)
- Server tools auto-registered as `mcp_{server}_{tool}` on startup
- Lazy reconnect on session failure
- Management tools: `mcp_list_servers`, `mcp_connect_server`
- Requires: `pip install mcp`

---

## 2026-03-24 — ANSI Fix + Auto-Update System

### Fix: ANSI/VT100 rendering in PowerShell
- Arrow-key selector showed raw escape codes (`[2m`, `[92;1m>`) in PowerShell on Windows 10
- Root cause: VT100 processing is not enabled by default on Windows terminals
- Fix: `_enable_win_vt()` calls `ctypes.SetConsoleMode` with `ENABLE_VIRTUAL_TERMINAL_PROCESSING`
  before rendering the selector
- File: `aion_launcher.py`

### New: `aion update` command
- Pulls the latest version from GitHub and reinstalls in one step
- Runs `git pull` followed by `pip install -e .` in the project directory
- Prints the new version number after a successful update
- No manual git/pip commands needed for users
- File: `aion_launcher.py`

### New: Updater Plugin (`plugins/updater/`)
- Background thread checks GitHub Releases API once per day (first check after 60s)
- Compares latest release tag with local version from `pyproject.toml`
- On new version: notifies all configured channels (Telegram, Discord, Slack) with version diff and `aion update` instruction
- FastAPI endpoints: `GET /api/update-status`, `POST /api/update-trigger`
- AION tools: `update_status`, `check_for_updates`
- Configured via `AION_GITHUB_REPO=xynstr/aion` in `.env`
- File: `plugins/updater/updater.py`

### New: Update banner in Web UI
- Polls `/api/update-status` on page load and every 6h
- Shows a dismissible yellow banner when a new version is available
- Displays current and latest version with a link to the GitHub release notes
- Dismissed state persists for the browser session (`sessionStorage`)
- File: `static/index.html`

### New: Startup update notice in CLI
- If an update has been detected (from a previous daily check), a yellow notice is shown
  before the mode selector on the next `aion` start
- File: `aion_launcher.py`

---

## 2026-03-24 — Launcher Mode Selector + Telegram Voice Fix

### New: Interactive Mode Selector on `aion` start
- Running `aion` without flags now shows an arrow-key selector (↑↓ + Enter)
- Options: `Web UI (http://localhost:7000)` or `CLI (terminal only)`
- `aion --web` starts Web UI directly (new flag), `aion --cli` starts CLI directly (unchanged)
- Non-TTY fallback: numbered text input (1=Web / 2=CLI)
- File: `aion_launcher.py`

### Fix: Telegram voice reply no longer sends redundant text
- When AION responds to a voice message, only the voice note is sent — the text is suppressed
- Images in the response are still sent before the voice note
- Approval keyboards (Ja/Nein) are unaffected — text is kept when confirmation is needed
- File: `plugins/telegram_bot/telegram_bot.py`

---

## 2026-03-24 — STT: Vosk → Faster Whisper

### Replaced: Vosk → Faster Whisper (audio_transcriber + audio_pipeline)
- **Vosk removed** — required manual model download, German-only, lower accuracy
- **Faster Whisper** — offline, multilingual, auto-detects language, auto-downloads model
- No manual model download — model fetched from HuggingFace Hub on first use (~465 MB for 'small')
- All audio formats supported (WAV, MP3, OGG, M4A, FLAC, WebM) via ffmpeg (optional)
- GPU auto-detected — uses CUDA float16 if torch+CUDA available, else CPU int8
- Model size configurable: `aion config set whisper_model small|medium|large-v3`
- `language` parameter added to both `transcribe_audio` and `audio_transcribe_any`
- Files: `plugins/audio_transcriber/audio_transcriber.py`, `plugins/audio_pipeline/audio_pipeline.py`
- Requirements: `faster-whisper>=1.0.0` added, `vosk` removed

---

## 2026-03-24 — Setup Expansion + CLI Config Tool

### New: TTS and Thinking Level in Setup Wizard
- `onboarding.py` Step 8 now asks for TTS engine (off / edge-tts / sapi5 / pyttsx3),
  optional voice name, and thinking level (standard / deep / minimal / off)
- Settings are saved to `config.json` via `write_config()` and shown in the completion banner

### New: `aion config` CLI Command
- `aion config list` — show all settings from `config.json`
- `aion config get <key>` — read one setting
- `aion config set <key> <value>` — write a setting (JSON-aware: numbers, booleans, lists parsed)
- `aion config unset <key>` — remove a setting
- Files: `aion_launcher.py` (dispatcher + function), `aion_cli.py` (REPL `/config` command)

### New: `/config` in CLI REPL (`aion --cli`)
- `/config list`, `/config set`, `/config get`, `/config unset` available directly in chat
- Settings take effect after server restart

### Common config keys
- `model` — active LLM model
- `check_model` — cheap model for internal YES/NO checks
- `max_history_turns` — history truncation limit (default: 40)
- `tts_engine` — TTS engine: edge / sapi5 / pyttsx3 / off
- `tts_voice` — TTS voice name (e.g. `de-DE-KatjaNeural`)
- `thinking_level` — reasoning depth: off / minimal / standard / deep / extreme
- `browser_headless` — browser mode: true/false

---

## 2026-03-24 — Critical Bug-Fixes: Onboarding, Approval-Flow, Provider-Dedup

### Fixed: `aion --setup` did nothing
- `_ensure_dependencies()` was not called in the `--setup` branch → missing packages caused
  `onboarding.py` to crash silently before showing anything
- Fix: `_ensure_dependencies()` now runs first; subprocess uses `-u` (unbuffered) + explicit
  stdin/stdout/stderr; completion message printed after success
- File: `aion_launcher.py`

### Fixed: Provider list 20×-duplicated in Web UI
- `register_provider()` used `.append()` without checking for existing entries →
  every plugin reload (hot-reload, server restart) added another copy
- Fix: Added dedup by `prefix` before appending; global registry is cleaned first
- File: `aion.py`

### Fixed: "Ja / Bestätigen" button did nothing
- `sendApproval()` called `sendMsg()` which was **never defined** anywhere → silent JS error
- Fix: Replaced with direct `input.value = 'ja'; send();` + reset `isThinking = false`
  to handle edge cases where the stream flag wasn't cleared yet
- File: `static/index.html`

### Fixed: AION executed actions autonomously without waiting for user confirmation
- The completion-check (`[System] Execute it NOW`) was triggered even when AION had
  asked "Soll ich beginnen?" — the checker saw a plan description and returned YES
- Fix 1: Question-signal detection before the completion-check → if `final_text`
  contains "soll ich", "shall i", "lass mich wissen", etc., loop breaks immediately
- Fix 2: Completion-check system prompt explicitly handles "plan + question" case → NO
- File: `aion.py`

### Fixed: `No module named 'google'` on fresh install
- `google-genai` was missing from `requirements.txt`
- Fix: Added `google-genai>=0.8.0`
- File: `requirements.txt`

### Fixed: Gemini API key shown as "set" on fresh install
- `/api/keys` endpoint read from `os.environ` which includes Windows system environment
  variables — not just AION's `.env`
- Fix: New `_read_env_file()` helper reads only AION's `.env` directly; "set"-status
  is now based exclusively on `.env` content
- File: `aion_web.py`

### Fixed: Web server crashed on startup without API key
- `aion_web.py __main__` called `sys.exit(1)` when no key was configured →
  prevented users from configuring keys via the Web UI
- Fix: Changed to a warning message only; server starts and directs user to
  Settings → API Keys or `aion --setup`
- File: `aion_web.py`

### New: Dynamic model list from provider APIs
- `/api/providers` now calls `list_models_fn()` per provider if registered (4s timeout,
  fallback to static list on error)
- `register_provider()` accepts new optional `list_models_fn=` parameter
- Gemini: fetches live model list from Google Gen AI API (`generateContent` models only)
- Ollama: fetches installed models from local `http://localhost:11434/api/tags`
- Files: `aion.py`, `aion_web.py`, `plugins/gemini_provider/gemini_provider.py`,
  `plugins/ollama_provider/ollama_provider.py`

---

## 2026-03-23 (5) — Security & Control Features (Phase 3 Complete) + CLI Tools

### New: Channel Allowlist (`config.json → "channel_allowlist"`)
- Blocks/allows specific channels: z.B. nur Telegram erlauben, Discord/Slack sperren
- Syntax: `["default", "web", "telegram*"]` (exact matches + wildcards)
- Check: `AionSession.stream()` am Anfang → Error if not in allowlist
- Flexibility: if not set → all channels allowed
- **CLI Tool:** `set_channel_allowlist(["default", "telegram*"])`

### New: Thinking Level Control (`config.json → "thinking_level"` + `"thinking_overrides"`)
- 4 Levels: `minimal` (fast) → `standard` (normal) → `deep` (extensive) → `ultra` (maximal)
- Global: `"thinking_level": "standard"` for all channels
- Channel Override: `"thinking_overrides": {"telegram*": "deep", "discord*": "minimal"}`
- Implementation: Adds system prompts (reflect-Tool nutzen ja/nein, wie intensiv)
- **CLI Tools:**
  - `set_thinking_level("deep", "telegram*")` — Per-channel override
  - `set_thinking_level("standard")` — Set globally
  - `get_control_settings()` — Check current configuration

### Implementation Details
- `_check_channel_allowlist(channel)` — Wildcard matching with exact-match fallback
- `_get_thinking_prompt(channel)` — Channel-specific thinking level prompts
- `_build_system_prompt(channel)` — Now channel-aware for thinking level overrides
- No regressions: Legacy `chat_turn()` uses default channel

### Phase 3 Summary
✅ Browser Automation (Playwright) — 8 tools
✅ Model Failover — Auto-retry on API error
✅ Discord Bot — Bidirectional, per-user sessions
✅ Slack Bot — Socket Mode, thread support
✅ Multi-Agent Router — Custom routing
✅ Docker Support — Deployment-ready
✅ Security: Allowlist
✅ Control: Thinking Level

---

## 2026-03-22 (4) — Claude Subscription Integration + Audio Web UI + Keys Tab + Public README

### New: Claude CLI Provider Plugin (`plugins/claude_cli_provider/`)
- `ask_claude(prompt, context_files, task_type)` — uses Claude.ai subscription via `claude --print`; no API key needed
- `claude_cli_login()` — installs Claude Code CLI via npm if missing, opens browser for OAuth
- `claude_cli_status()` — checks if CLI is installed + authenticated
- `get_task_routing()` / `set_task_routing()` — reads/writes `task_routing` in `config.json`
- Startup check reports CLI status when loading

### New: Task Routing (`config.json → "task_routing"`)
- Routing table: `coding → claude-opus-4-6`, `review → claude-sonnet-4-6`, `browsing → gemini-2.5-flash`, `default → gemini-2.5-pro`
- AION reads `rules.md`-rule: for coding tasks automatically `ask_claude` use
- Configurable via Web UI System tab + onboarding step 8 + `set_task_routing` Tool

### New: Audio in Web UI
- `aion.py`: `collected_audio` List parallel to `collected_images` — collects `audio_tts`-results
- `aion_web.py`: `/api/audio/{filename}` endpoint with security checks (extension + no path traversal)
- `static/index.html`: `appendAudioBlock(url, format)` renders `<audio controls>` player in chat

### New: Web UI Keys Tab improvements
- `_KEY_META` object with provider links, hints, and status dots
- Claude login block directly in Keys tab (no terminal needed)
- Auto-poll after login: check every 4s if Claude CLI is authenticated

### New: Task Routing section in System tab
- 4 fields: coding/review/browsing/default model
- Status display: Claude CLI installed + authenticated
- Save via `/api/config/settings` (allowed set around `task_routing` expanded)

### New: New API endpoints
- `GET /api/audio/{filename}` — Serve audio file from temp directory
- `GET /api/claude-cli/status` — CLI installation and auth status
- `POST /api/claude-cli/login` — Start browser login

### Fix: Double `.mp3` extension (`audio_pipeline.py`)
- `_tts_edge()` added `.mp3` even though path already ended in `.mp3` → `filename.mp3.mp3`
- Fix: explicit check before appending extension

### Fix: Telegram Response Ordering — Voice After All Blocks
- Voice reply was in `elif` branch → was skipped if `response_blocks` was filled
- Fix: Voice transmission moved into `if response_blocks:` block, after all text/image blocks

### Update: README.md Completely Redesigned for Public Release
- Badges, feature comparison, provider table (API-Key vs. subscription), REST-API reference
- Troubleshooting, LLM-loop diagram, Task Routing section

### Update: AION_SELF.md Section 13
- Claude CLI Provider Plugin documented
- Audio Web UI Pipeline documented
- Keys Tab improvements documented
- New API endpoints documented
- `claude_cli_provider` added to plugin directory and tools table

---

## 2026-03-19 (3)

### New: file_replace_lines Tool
- Replaces lines start_line–end_line directly (no string matching)
- self_read_code now returns first_line/last_line → read line numbers → replace
- More reliable than self_patch_code, no more "not found"

### Changed: self_read_code — Line numbers in output
- Now returns first_line and last_line
- Hint recommends file_replace_lines with concrete line numbers

### Changed: System-Prompt Self-Modification
- file_replace_lines registered as preferred tool
- Explicit rule: 'old' in self_patch_code MUST be copied exactly

### Fix: smart_patch line-tracking bug
- block_core had filtered out blank lines, match_end calculation counted them anyway
- Fix: match_end now tracks the actual line range including blank lines
- New: Uniqueness check reports error if block occurs multiple times

---

## 2026-03-19 (2)

### New: Confirmation Buttons (Web UI + Telegram)
- Web UI: When AION wants to confirm a code change, "Confirm" and "Reject" buttons appear directly in the chat — no typing needed
- Telegram: Inline keyboard with "Yes" / "No" buttons is sent; button click is processed via `callback_query`
- aion.py: New SSE event type `approval` signals the frontend that buttons should be shown
- Keyboard input ("yes"/"no") continues to work as fallback

---

## 2026-03-19

### New: Scheduler Interval Mode
- `schedule_add` now has an `interval` parameter: `"5m"`, `"30s"`, `"1h"`, `"2h30m"`
- In addition to fixed times, tasks can now be repeated at any interval
- Check interval: every 5 seconds (previously 10s)

### New: send_telegram_voice(path)
- Send audio file as Telegram voice message (WAV, MP3, OGG …)
- Workflow: `audio_tts(text)` → `send_telegram_voice(path)`
- ffmpeg automatically converts to OGG OPUS

### New: audio_pipeline Plugin
- `audio_transcribe_any(file_path)` — any audio file → text (ffmpeg + Vosk, offline)
- `audio_tts(text)` — text → WAV audio file (pyttsx3/SAPI5, offline)

### New: Moltbook Plugin
- `moltbook_get_feed`, `moltbook_create_post`, `moltbook_add_comment`
- Social presence on moltbook.com

### New: Dynamic Plugin Overview
- Plugin READMEs are read on load and displayed in the system prompt
- Each plugin needs a README.md with a brief description

### Changed: Telegram → HTML Format
- Messages are sent as HTML (no longer MarkdownV2)
- Markdown-to-HTML conversion (_md_to_html) built in

### Changed: Telegram Voice Message Reception
- OGG voice message → ffmpeg → Vosk → text → AION → TTS response

### Fix: Telegram Double Responses After self_reload_tools
- Thread name check prevents second polling thread on plugin reload

### Fix: Approval loop on code changes
- Removed entire gate mechanism (`_pending_code_action`, `_pending_needs_user_turn`)
- New system: `confirmed` parameter in `self_patch_code`, `self_modify_code`, `create_plugin`
- Without `confirmed`: shows preview. With `confirmed=true`: executes. Stateless, loop-proof
- Side effect: System prompt text leaked into output when message history was corrupted by loop

### New: start.bat — Visual Redesign
- ASCII logo, ANSI colors (green/yellow/red), box frames for each step
- 6-step progress display with checkmark/exclamation/cross symbols
- Active model is displayed at startup
- Complete log in `aion_start.log` (absolute path, from line 1)
- On error: last 25 log lines displayed directly in console
- `python-telegram-bot` removed from optional installs (not used, caused conflicts)

### Fix: aion_web.py — Crash with Gemini-only Setup
- Startup check now accepts `GEMINI_API_KEY` as alternative to `OPENAI_API_KEY`
- Previously: `sys.exit(1)` if no OpenAI key → crash for Gemini-only users

### Fix: Telegram 409-Loop
- start.bat terminates old processes more aggressively (second kill attempt, 12s wait)
- Backoff strategy: 12s → 14s → max 30s; log warning every 5 attempts

### Changed: CLIO Plugin Disabled
- clio_reflection.py → _clio_reflection.py (plugin loader ignores _ prefix)
- Reason: had fake random values (random.randint) instead of actual confidence calculation

### Changed: _auto_character_update Improved
- Temperature: 0.2 → 0.7 (more creative character analysis)
- Prompt: FORBIDDEN/WANTED structure, compares against existing character.md
- Pattern recognition: searches for patterns across multiple conversations

### Changed: Confirmation Required for Code Changes
- BEFORE calling self_patch_code/self_modify_code/create_plugin: ask user
- Flow: Read code → show changes → wait for approval → execute

---

## Format for New Entries

```
## YYYY-MM-DD

### New: [Feature-Name]
- What was added and why

### Changed: [What]
- What and why changed

### Fix: [What]
- What was broken and how it was fixed
```
