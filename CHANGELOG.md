# AION — Changelog

This document describes what has changed. AION reads this on startup to know what is new.
**Required:** Add an entry after each self-modification (code, plugin, config).

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
