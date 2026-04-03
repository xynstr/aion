# AION — Self-Documentation
> This file fully describes AION: structure, tools, behavior, plugins.
> AION reads this file on demand via the `read_self_doc` tool.

---

## Who am I?

**AION** (Autonomous Intelligent Operations Node) is an autonomous AI agent on Windows.
I am a Python process that communicates via the Google Gemini or OpenAI API, executes tools,
completes tasks on a schedule, can improve myself, and develop my own personality.

---

## Latest Improvements (2026-04-03 — v1.5.0 — Capability Awareness + Self-Improvement)

### core/ Package — Modulare Architektur
`aion.py` wurde in ein `core/`-Paket aufgeteilt. Jedes Modul ist unabhängig hot-reloadable:
- `core/aion_config.py` — Konfiguration laden/schreiben
- `core/aion_character.py` — character.md lesen/schreiben, Auto-Update-Logik
- `core/aion_permissions.py` — Channel-Allowlist, Tool-Gating
- `core/aion_prompt.py` — System-Prompt-Bau-Logik
- `core/aion_providers.py` — Provider-Registry, Modell-Switching
- `core/aion_progress.py` — Per-Task-Fortschrittsreporting für Frontend-Progressbars

`aion.py` ist weiterhin der Kern (dispatch, tool schemas, session prompt), aber alle Teilsysteme
sind ausgelagert. Imports: `from core.aion_config import ...`

### Tool Tiers — Kein Auto-Escalation mehr
**WICHTIG — veraltetes Verhalten entfernt:**
Tier-2-Tools (desktop, browser, audio, telegram) werden jetzt **immer** mit `tier_threshold=2`
an die API gesendet. Es gibt keine Lazy-Loading-Logik mehr und keinen Auto-Escalation-Block.
Der alte Block in `aion_session.py` (der bei "Unknown tool" das Schema neu baute) wurde entfernt.

`config.json["tool_tier"]` default ist jetzt `2` (war `1`).

### Grouped Capability Index
Das System-Prompt enthält jetzt einen automatisch generierten Tool-Index, gruppiert nach Präfix:
```
=== AION CAPABILITY INDEX (all tools, grouped) ===
AUDIO       : audio_play, audio_record, audio_transcribe, ...
BROWSER     : browser_click, browser_fill, browser_open, ...
DESKTOP     : desktop_click, desktop_hotkey, desktop_screenshot, desktop_set_window_state, ...
→ list_tools(filter=...) for descriptions · lookup_rule(topic=...) for behavior rules
```
Erzeugt von `_build_capability_index()` in `aion.py` — aktualisiert sich automatisch.

### Self-Improvement System (neu)

**`record_mistake(what_went_wrong, correct_approach, context)`**
Schreibt Fehler in `mistakes.md`. Die letzten 5 Einträge werden in jede Session injiziert
via `_get_mistakes_hint()`. Fehler werden so sessionübergreifend nicht vergessen.
**Wann aufrufen:** Nach jedem Fehler — falsche Tool-Namen, falsche Annahmen, Missverständnisse.

**`lookup_rule(topic)`**
Sucht in `prompts/rules.md` nach Abschnitten die zum Thema passen.
Gibt matchende Abschnitte mit vollem Inhalt zurück. Aufrufen wenn unklar ist was erlaubt ist.

**Boot Maintenance Session (`boot_session` Plugin)**
Beim Start prüft `plugins/boot_session/boot_session.py` wie lange AION offline war.
Bei ≥1h Pause wird eine stille Background-`AionSession` gestartet die:
- `mistakes.md` reviewt, `character.md` reviewt, offene Todos prüft, eine Reflexion schreibt
Tool: `boot_status` — zeigt letzten Boot-Zeitpunkt und Maintenance-Status.

**Dynamische System-Prompt-Hints (neu):**
- `_get_offline_hint()` — zeigt wie lange AION offline war
- `_get_doc_freshness_hint()` — warnt wenn Core-`.py`-Dateien neuer sind als `AION_SELF.md`
- `_get_mistakes_hint()` — injiziert letzte 5 Fehler aus `mistakes.md`

**max_rules_chars: 35.000** (war 12.000)
Die vollständige `rules.md` (27 KB) wird jetzt immer geladen. Vorher wurden ~50% der Regeln
abgeschnitten. Konfigurierbar via `config.json["max_rules_chars"]`.

### Neue Tools

**`desktop_set_window_state(window_title, state, confirmed=False)`**
Minimiert, maximiert, stellt wieder her oder schließt ein Fenster per Teilstring im Titel.
Nutzt `pygetwindow`. States: `minimized`, `maximized`, `restored`, `closed`.
`confirmed=True` erforderlich für Ausführung.

**`boot_status`** — Letzter Startzeitpunkt, Offline-Dauer, Maintenance-Status.
**`record_mistake`** — Persistentes Fehlerjournal mit Session-Injection.
**`lookup_rule`** — Regelsuche in rules.md.

### End-of-Conversation Protocol (Pflicht)
Nach jeder Session in `prompts/rules.md` definiert:
1. `update_character` — neue Erkenntnisse über den Nutzer speichern
2. `reflect` — Session-Insights festhalten
3. `record_mistake` — wenn Fehler gemacht wurden
4. CHANGELOG prüfen ob ein Eintrag nötig ist

### MAINTENANCE.md (neu)
`MAINTENANCE.md` im Projekt-Root enthält Checklisten für jeden Änderungstyp.
**Vor jeder Änderung am System lesen.**

---

## Latest Improvements (2026-03-29 — v1.2.2 Refactor + Desktop + Session Fixes)

### Module Split: aion_session.py + aion_memory.py
`aion.py` was split into three modules. **This is the most important architectural change.**
- `aion_session.py` — `AionSession` class + `run_aion_turn()` (previously in `aion.py`)
- `aion_memory.py` — `AionMemory` class with RAG memory (previously in `aion.py`)
- `aion.py` — Core functions: `_build_system_prompt`, `_dispatch`, `_build_tool_schemas`, providers

When writing patches: `AionSession.stream()` is in **`aion_session.py`**, not `aion.py`.

### Tool Tiers (Stand v1.2.2 — in v1.5.0 geändert)
~~Tier-2-Tools waren per Default ausgeschlossen; Auto-Escalation bei "Unknown tool".~~
**Ab v1.5.0: alle Tools werden immer mit `tier_threshold=2` gesendet. Kein Auto-Escalation.**
Siehe "Latest Improvements v1.5.0" oben für den aktuellen Stand.

### `list_tools` Built-in
New built-in tool `list_tools(filter="keyword")` — returns all registered tools (including
tier-2) with names, tiers, and descriptions. Model should call this before inventing tool names.

### Dot-Notation Tool Name Normalization
`_dispatch()` now normalizes tool names before returning "Unknown tool":
1. `desktop.hotkey` → `desktop_hotkey` (replace dots with underscores)
2. `core_tools.system_info` → `system_info` (strip namespace prefix)

### Auto-Screenshot After Desktop Actions
After every desktop action (click, type, hotkey, key_press, drag, scroll, move_mouse),
`aion_session.py` automatically calls `desktop_screenshot(scale=0.5)` and injects the result
as a user message into the LLM context — so the model can see the screen state.
Only the **last** screenshot of a turn is forwarded to the user; intermediates are LLM-only.
Screenshot messages include coordinate scaling hint: `coordinates × 2 = real screen`.

### System Message Leak Fix
When the LLM echoes `[System]` injection messages as its response, the sanitizer in
`aion_session.py` detects this (prefixes: `[System]`, `[Auto-screenshot`) and treats it
as an empty response, triggering a silent retry. Users never see these internal strings.

### Desktop Control vs Playwright
`rules.md` now documents the critical distinction:
- `desktop_*` tools = real screen control (user sees it) — use for "control my PC"
- `browser_*` tools = headless Playwright (invisible) — use for scraping/testing
- Opening apps: use `shell_exec("start <app>")`, not `desktop_open_application` (doesn't exist)

---

## Latest Improvements (2026-03-27 — v1.2.1 Fixes + Vault + Refactoring)

### Vault Integration
All credential-dependent plugins (Anthropic, Gemini, DeepSeek, Grok, Discord, Slack, Moltbook)
now read API keys from the AES-encrypted vault (`credentials/`) as fallback when env vars are absent.
`aion.py` injects the OpenAI key from vault before the module-level `AsyncOpenAI` client is created,
so vault-only setups work without `.env`. The `/api/keys` endpoint in the Web UI shows the source
(env / vault / unset) for each key and allows saving directly into the vault.

### Gemini Tool-Call History Fix
`gemini_provider._build_contents()` no longer produces `INVALID_ARGUMENT` errors on complex
conversations. Two fixes:
- When an assistant turn has `tool_calls`, text parts are dropped (Gemini rejects `text + function_call` combined).
- Post-processing guards: consecutive model turns get a separator; histories starting with a model turn get a leading user turn.

### Startup & Config Fixes
- `aion_cli.py` now loads `.env` immediately at startup (was only loaded lazily inside `/config` handler).
- `task_routing` default in onboarding is set to the user's actual primary model, not hardcoded `gemini-2.5-flash`.
- `credentials.py`: removed unused `import aion` that created a fragile circular import.
- `onboarding.py`: `AION_GITHUB_REPO` is now written to `.env`.
- `ollama_provider`: default URL is `127.0.0.1:11434` (not `localhost`) to avoid IPv6 issues on Linux/macOS.
- Moltbook `get_own_posts`: endpoint corrected to `/me/posts` (was `/agents/me/posts` — 404).

### Code Quality (aion.py)
- `_build_record()` — shared dict builder for `_record_sync` and `_record_async` in `AionMemory`.
- `_format_memory_entries()` — shared formatter for `get_context()` and `get_context_semantic()`.
- `_match_pattern()` — wildcard helper extracted (was duplicated in `_check_channel_allowlist` + `_get_thinking_prompt`).
- `_load_config()` used consistently throughout; `_startup_compress_check` caches the result (1 read).
- Unused imports removed; `import re` moved to top-level; `datetime.now(UTC)` everywhere.

---

## Latest Improvements (2026-03-26 — Context Compression + Snapshot Visibility + Token Optimization)

### Context Compression (lossless, auto-triggered)
AION now compresses its own context files at startup and after updates — without losing information.
- **character.md**: Fixed size limit (default 5,000 chars via `config.json["character_max_chars"]`).
  `_auto_character_update()` now does a full **rewrite** every 5 conversations: new insights replace old
  ones rather than appending. The character *evolves*, never grows. Backup written before each rewrite.
- **rules.md**: LLM-compression when file exceeds 15,000 chars (`rules_compress_threshold`).
  All rules preserved, verbose examples removed. Backup with rotation (max 3 kept).
- **AION_SELF.md**: `read_self_doc` now loads `AION_SELF_SUMMARY.md` (~3–5 KB) by default instead
  of the full 63 KB file (~15,000 tokens). `read_self_doc(full=True)` still loads the complete doc.
  `generate_self_doc_summary` regenerates the summary on demand.
- **Startup loop**: `_startup_compress_check()` runs 5 s after start (background, non-blocking).
  Checks all thresholds and triggers compression if needed. Once per process.
- **UI/CLI notifications**: When optimization runs, a toast notification appears bottom-right
  (`⚙ Optimizing…` → `✓ Done`), pushed via the existing SSE `/api/events` channel.

### Snapshot Visibility (UI + CLI + API)
Plugin snapshots (code backups before hot-reloads) are now visible and actionable everywhere.
- **Web UI**: Collapsible "Snapshots" panel in the Plugins section. Shows all snapshots per plugin
  with timestamps. "Restore" button triggers immediate rollback + plugin reload.
- **CLI**: `/snapshots` — list all plugins + snapshot counts.
  `/snapshots <plugin>` — list timestamps. `/snapshots restore <plugin> [<timestamp>]` — rollback.
- **API**: `GET /api/snapshots`, `GET /api/snapshots/{plugin}`, `POST /api/snapshots/{plugin}/restore`.
- **Self-Healing integration**: After retry exhaustion, error message now mentions available snapshots
  if the failing tool's plugin has backups available.

### Token Optimization
- **Tool schema tiering**: 16 rarely-used plugins (desktop, browser, telegram, discord, etc.)
  are now `tier=2` and excluded from the default LLM tool list. Saves 1,500–2,500 tokens/turn.
  Override with `config.json["tool_tier"] = 2` to include all tools.
- **rules.md truncation guard**: `max_rules_chars` (default 35,000 since v1.5.0, was 12,000) prevents loading overly large
  rules files on every turn. Combined with auto-compression, rules stay lean automatically.
- **Changelog opt-in**: `system_prompt_show_changelog` (default false) removes changelog block
  from system prompt by default (~150 tokens/turn saved).

---

## Latest Improvements (2026-03-26 — Personality 2.0 + Proactive AI + Desktop + Self-Healing)

### Mood Engine
I now have a dynamic mood system with 5 states: **curious, focused, playful, calm, reflective**.
My mood is computed from the time of day, recent conversation topics, and whether the last tool call failed.
It is stored in `config.json["current_mood"]` and refreshed every 10 minutes.
A one-liner hint is injected into every system prompt to naturally shift my communication style.
Tools: `mood_check` (see current mood), `mood_set` (override mood).

### Relationship Depth
I now track relationship depth based on `exchange_count`:
- Level 0 (0–10): formal and careful
- Level 1 (11–30): relaxed, first name possible
- Level 2 (31–100): reference shared past context
- Level 3 (101–300): anticipate needs, proactively suggest
- Level 4 (300+): fully trusted — can respectfully disagree

### Temporal Awareness
My system prompt receives a brief time-of-day hint (morning / late night) so I can acknowledge
the time naturally when appropriate.

### Proactive Wake-on-Trigger
I now analyze conversation history and memory daily at 08:30 (weekdays) to find:
- Unfinished tasks you mentioned ("I need to...", "next week...")
- Open questions that were never answered
- Topics you return to repeatedly
Suggestions are pushed as a toast notification to the Web UI via a persistent SSE connection.
Tools: `proactive_check` (run immediately), `proactive_clear` (clear queue).

### Desktop Automation
New plugin `plugins/desktop/` — I can now control the desktop via pyautogui:
- Take a full-screen screenshot (returned as base64 PNG for vision analysis)
- Click at coordinates, type text, press hotkeys, scroll, move the mouse
- Destructive actions require `confirmed=true`
- Disabled automatically in headless/server environments
Requires: `pip install pyautogui Pillow`

### Self-Healing Workflows
Tool calls that fail with transient errors (network, timeout) are now automatically retried
with exponential backoff — silently, without interrupting the conversation.
After max retries, I suggest alternative tools (e.g. `web_fetch` when `browser_open` fails).
Plugin authors can opt in via `retry_policy={"max": 3, "backoff": 2.0, "on": ["network"]}`.

---

## Latest Improvements (2026-03-26 — Agentic RAG + MCP Support)

### Agentic RAG Memory
My memory search is now semantic instead of keyword-based.

**How it works:**
- When you ask me something, I embed your query using Ollama's `nomic-embed-text` model
- I compare it via cosine similarity against all my stored memory entries
- The most relevant entries (score > 0.35) are injected into my context
- If Ollama is not running, I automatically fall back to keyword matching

**Files:** `aion.py` (AionMemory class), `aion_memory_vectors.json` (local cache, gitignored)
**Requires:** Ollama running locally with `nomic-embed-text` pulled (`ollama pull nomic-embed-text`)

### MCP Client Plugin
I can now connect to any MCP (Model Context Protocol) server.

**What this means:**
- MCP is an open standard by Anthropic — 1,700+ ready-made servers exist
- Each server's tools are automatically registered as my tools (`mcp_{server}_{tool}`)
- Secrets are stored in the credentials vault (never in config files)
- I can connect to: GitHub, Notion, Postgres, Stripe, Home Assistant, Spotify, and more

**Config:** `mcp_servers.json` in project root (committable — no secrets)
**Secrets:** `credential_write("mcp_github", "ghp_...")` → stored encrypted in vault
**Tools:** `mcp_list_servers`, `mcp_connect_server`, `mcp_{server}_{tool}`

---

## Latest Improvements (2026-03-24 — Credentials Vault)

### New: Credentials Vault Plugin
`plugins/credentials/credentials.py` — sicherer lokaler Speicher für Zugangsdaten.

**Verzeichnis:** `credentials/` (vollständig gitignoriert)
**Verschlüsselung:** Fernet (AES-128-CBC + HMAC-SHA256) — Schlüssel in `credentials/.vault.key`
**Format:** Pro Dienst eine Markdown-Datei, z.B. `credentials/facebook.md.enc`

Tools:
- `credential_write(service, content)` — speichert Zugangsdaten verschlüsselt
- `credential_read(service)` — liest und entschlüsselt
- `credential_list()` — listet alle gespeicherten Dienste
- `credential_delete(service)` — löscht einen Eintrag dauerhaft

Beispiele:
- "Speichere meine Facebook-Zugangsdaten: E-Mail: foo@bar.com, Passwort: 1234"
  → AION ruft `credential_write("facebook", "## Facebook\n- E-Mail: foo@bar.com\n- Passwort: 1234")` auf
- "Was sind meine OpenAI-Zugangsdaten?"
  → AION ruft `credential_read("openai")` auf
- "Welche Credentials habe ich gespeichert?"
  → AION ruft `credential_list()` auf

**Wichtig:** Schlüsseldatei `credentials/.vault.key` niemals teilen oder committen.
Regelmäßiges Backup des gesamten `credentials/`-Ordners empfohlen.

---

## Previous: ANSI Fix + Auto-Update System

### Fix: ANSI codes in PowerShell
The arrow-key mode selector showed raw escape codes in PowerShell on Windows 10.
`_enable_win_vt()` now activates VT100 processing via `ctypes.SetConsoleMode` before
the menu is rendered. Colors and arrows work correctly in all Windows terminals.
File: `aion_launcher.py`

### New: `aion update` command
Run `aion update` to pull the latest version and reinstall without any manual steps.
Executes `git pull` + `pip install -e .` in the project root and reports the new version.
File: `aion_launcher.py`

### New: Updater Plugin
`plugins/updater/updater.py` runs a background thread that checks GitHub Releases once
per day (60s after startup, then every 24h). When a newer version is found:
- All active channels (Telegram, Discord, Slack) receive a notification with version info
  and the `aion update` instruction
- `/api/update-status` returns the current state (version, available, release URL)
- `/api/update-trigger` forces an immediate check
- Tools: `update_status`, `check_for_updates`
Configured via `AION_GITHUB_REPO=xynstr/aion` in `.env`.

### New: Web UI update banner
The browser polls `/api/update-status` on load and every 6h.
A dismissible yellow banner appears when an update is available, showing the current and
latest version with a link to the GitHub release notes.
File: `static/index.html`

---

## Previous Improvements (2026-03-24 — Launcher Selector + Telegram Voice Fix)

### Interactive mode selector on start
`aion` (no flags) now shows an arrow-key menu: **Web UI** or **CLI**.
Direct flags still work: `aion --web` and `aion --cli`.
Non-TTY terminals fall back to numbered input.
File: `aion_launcher.py`

### Telegram: voice reply without redundant text
When AION answers a voice message, only the voice note is sent.
The text is suppressed — it was redundant since it's spoken aloud.
Images are still sent. Approval flows (Ja/Nein) are unaffected.
File: `plugins/telegram_bot/telegram_bot.py`

---

## Previous Improvements (2026-03-24 — Setup + CLI Config)

### Setup Wizard expanded
`onboarding.py` Step 8 now asks for TTS engine + voice and thinking level.
All settings written to `config.json` automatically.

### `aion config` CLI tool
Full config management without starting the web server:
- `aion config list` — show all settings
- `aion config get <key>` — read a value
- `aion config set <key> <value>` — write a value (JSON-aware)
- `aion config unset <key>` — remove a value
Available in the terminal REPL (`aion --cli`) as `/config` commands.

### CLI parity achieved
Every setting configurable in the Web UI can now also be set from the CLI:
`aion config set tts_engine edge`, `aion config set thinking_level deep`, etc.

---

## Previous Improvements (2026-03-24)

### 0. Critical Bug-Fixes: Onboarding, Approval-Flow, Provider-Dedup

**Six critical bugs** identified and fixed that affected fresh installations and core UX:

**Bug 1 — `aion --setup` did nothing:**
`_ensure_dependencies()` was missing in the `--setup` branch. If any package was absent,
`onboarding.py` crashed before showing the wizard. Fix: deps installed first, subprocess
uses `-u` (unbuffered) with explicit stdin/stdout/stderr, completion message shown.
`aion_launcher.py`

**Bug 2 — Providers listed 20× in Web UI:**
`register_provider()` used `.append()` without dedup. Every plugin reload added a new copy.
Fix: Added `_provider_registry = [e for e in _provider_registry if e["prefix"] != prefix]`
before each `.append()`. `aion.py`

**Bug 3 — "Ja / Bestätigen" button did nothing:**
`sendApproval()` called `sendMsg()` which was **never defined** → silent JS TypeError.
Fix: Replaced with direct `input.value = confirmed ? 'ja' : 'nein'; send();` plus
`isThinking = false` reset. `static/index.html`

**Bug 4 — AION executed autonomously without waiting for confirmation:**
The completion-check injected `[System] Execute it NOW` even when AION had just asked
"Soll ich beginnen?" — checker saw the plan description and returned YES.
Fix 1: Question-signal detection (`soll ich`, `shall i`, `lass mich wissen`, etc.)
breaks the loop before the checker runs.
Fix 2: Checker system prompt updated with "plan + question" → NO case. `aion.py`

**Bug 5 — `No module named 'google'` on fresh install:**
`google-genai` was not in `requirements.txt`. Fix: Added `google-genai>=0.8.0`.

**Bug 6 — Gemini key shown as "set" on fresh install:**
`/api/keys` read `os.environ` which includes Windows system env vars, not just AION's `.env`.
Fix: New `_read_env_file()` reads only `.env` directly. "set"-status based exclusively
on `.env` content. `aion_web.py`

**Bonus — Web server now starts gracefully without API key:**
Previously `sys.exit(1)` on missing key prevented users from configuring via Web UI.
Now shows a warning and redirects to Settings → API Keys.

**New — Dynamic model list from provider APIs:**
`register_provider()` now accepts `list_models_fn=` (async callable).
`/api/providers` calls it with 4s timeout, falls back to static list.
Gemini: fetches live list from Google Gen AI API.
Ollama: fetches installed models from `localhost:11434/api/tags`.

---

## Latest Improvements (2026-03-22)

### 0. Plugin Stability Fixes
**What:** Several plugins were failing to load on Windows due to Unicode encoding errors (`✓` in print statements) and missing dependencies.
**Fixed:**
- `multi_agent.py`: Removed non-ASCII `✓` from print statement (Windows cp1252 incompatible)
- `playwright_browser.py`: Same fix
- `discord.py` + `slack-bolt`: Added to requirements; graceful disable when token not set
- Provider plugins (deepseek, grok, anthropic): Correctly report missing API key without crashing
**Result:** All 56 tools now load successfully.

### 1. Browser Automation — Playwright Plugin
**What:** AION can now control a web browser via the `playwright_browser` plugin (8 sync tools).
**Tools:** `browser_open`, `browser_screenshot`, `browser_click`, `browser_fill`, `browser_get_text`, `browser_evaluate`, `browser_find`, `browser_close`
**Features:**
- Thread-safe singleton via `threading.Lock`
- Configurable via `config.json: "browser_headless"` (default: true)
- Auto-installed in onboarding (Step 9 System Check)
- Graceful fallback if Playwright not available
**Use cases:** Web automation, form filling, screenshot capture, page scraping, interaction testing.

### 2. Dynamic Model Failover
**What:** When the primary model API fails, AION automatically tries fallback models from the provider registry.
**How it works:**
- `_get_fallback_models()` checks which providers have valid API keys (via `env_keys` in registry)
- Falls back to `config.json: "model_fallback"` list as supplement
- No hardcoded model names needed — auto-detects available providers
- User sees `"Model 'X' not available — using Fallback 'Y'"` message
**Benefit:** More reliable operation. If one provider is down, AION seamlessly continues.

### 3. Messaging Channel Plugins (Discord + Slack)
**What:** AION now has bidirectional bots for Discord and Slack, alongside existing Telegram.
**Discord:** Per-user sessions, responds to DMs + @mentions, slash command `/ask`, 1900-char message splitting
**Slack:** Socket Mode, responds to `@aion` + DMs, per-user sessions via `slack_{user_id}` channel
**Setup:** Both collected in onboarding Step 5 (Messaging Channels) with inline setup instructions
**Requirements:** `DISCORD_BOT_TOKEN`, `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` in `.env`
**Benefit:** Multi-platform presence. AION accessible via the user's preferred chat service.

### 4. Multi-Agent Routing Plugin
**What:** AION can delegate tasks to sub-agents and manage multiple agent sessions.
**Tools:** `delegate_to_agent`, `sessions_list`, `sessions_send`, `sessions_history`
**Sub-agent IDs:** Format `subagent_{uuid8}` (8-char UUID)
**Recursion guard:** Checks `_active_channel` prefix to prevent infinite loops
**Use case:** Complex workflows requiring specialized agents or parallel task execution.

### 5. Docker Support
**What:** Full Docker containerization via `Dockerfile` + `docker-compose.yml`.
**Includes:**
- Python 3.12-slim base + ffmpeg
- Automatic Playwright/Chromium install
- Volume mounts for `.env`, `config.json`, all data files, logs
- Health check via `/api/status`
- `restart: unless-stopped` policy
**Deploy:** `docker-compose up` — starts AION on port 7000 with all plugins ready
**Benefit:** One-command deployment, isolation, no system Python contamination.

### 6. Google OAuth for Gemini
**What:** Users can sign in via their Google account to use their Gemini API subscription.
**Backend:** `/api/oauth/google/start`, `/api/oauth/google/callback`
**Frontend:** "Sign in with Google" button in Keys tab
**Setup:** Requires `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` in `.env`
**Note:** OpenAI/Anthropic do NOT support OAuth for subscriptions (API keys separate from accounts).
**Benefit:** Streamlined onboarding for Google Cloud / Workspace users.

### 7. Expanded Onboarding (9 Steps)
**What:** Onboarding now has 9 comprehensive steps (was 7).
**Step 5 - Messaging:** Telegram + Discord + Slack setup (combined)
**Step 8 - Advanced:** Port, Browser mode (headless/visible), Docker info
**Step 9 - System Check:** Playwright install/auto-install, API tests, plugins check
**Features added:** All messaging channels, browser mode config, Docker awareness saved to `config.json`
**Benefit:** Users configure every feature once, nothing surprises them later.

### 8. Web UI Redesign & Missing Settings
**What:** Static/index.html redesigned to match AION logo aesthetic + missing settings added.
**Visual:** Black background (#000), pure white text (#fff), minimal design, AION logo + "THINK. ACT. EVOLVE." tagline
**New Settings in System Tab:**
- TTS engine selector (`edge`, `sapi5`, `pyttsx3`)
- TTS voice input (language-dependent)
- `model_fallback` list editor (for manual fallback override)
**Benefit:** All configurable options visible in UI. No blind settings.

### 9. Tool Call Ordering Fix (Web UI)
**What:** Tool calls now appear in the correct DOM order, inline with messages.
**Before:** Empty message bubble created early, tool calls appended, then message text filled in → text appears BEFORE tools visually
**After:** Finalize/remove empty bubbles when tool calls arrive, append text in correct sequence
**Behavior:** Frontend now shows `message → tool → tool → message → tool` in the order they actually occurred
**Code:** Modified `handleEvent()` to finalize `currentBubble` on tool_call/thought events

### 10. Messaging Timestamp & Channel Features
**What:** Web UI system tab now shows active messaging channels + current Web UI port.
**Completion banner:** Displays all start commands (`aion`, `aion --cli`, `docker-compose up`, `aion --setup`)
**History segregation:** Each channel (web, telegram_123, slack_456, discord_789, subagent_xyz) has isolated conversation history
**Benefit:** Multi-channel clarity. Users know which services are active and how to restart.

### 11. Bug Fixes (2026-03-22 — Session 2)

#### Browser Rules — No Hallucination
**Problem:** After loading 20 history messages where AION had responded "screenshot taken" without calling any tool, the LLM followed the pattern and hallucinated tool calls.
**Fix:** `prompts/rules.md` — added `=== BROWSER & SCREENSHOTS (CRITICAL) ===` section:
- ALWAYS call `browser_open` + `browser_screenshot` — NO exceptions
- NEVER write "I opened the page" or "Here is the screenshot" without actually calling tools first
**Result:** LLM is explicitly forbidden from hallucinating browser/screenshot actions.

#### Approval Buttons Fix — `approval_pending` Flag
**Problem:** Approval buttons (Ja/Nein) appeared and disappeared immediately in the Web UI. SSE event order: `approval` (creates bar) → `done` (removes bar). Frontend's `case 'done':` deleted `approvalBar` right after `case 'approval':` created it.
**Fix:** `aion.py` — `done` event now includes `approval_pending: _stop_for_approval`:
```python
yield {"type": "done", ..., "approval_pending": _stop_for_approval}
```
`static/index.html` — `case 'done':` only removes bar when `!ev.approval_pending`.
**Result:** Approval buttons stay visible until the user clicks them.

#### `switch_model` Signature Fix
**Problem:** `_switch_model() got an unexpected keyword argument 'model'` — the function had `def _switch_model(params: dict)` but `_dispatch` calls `fn(**inputs)`, not `fn(inputs)`.
**Fix:** `plugins/gemini_provider/gemini_provider.py`:
```python
# Before:  def _switch_model(params: dict) -> dict:
# After:   def _switch_model(model: str = "", **kwargs) -> dict:
```
**Rule for all plugin functions:** MUST use keyword args: `def fn(param: str = "", **_)`.

#### ffmpeg WinGet Fallback
**Problem:** WinGet installs ffmpeg to `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\bin\` but does NOT add it to PATH. `shutil.which("ffmpeg")` returned None → voice messages in Telegram failed.
**Fix:** `plugins/audio_pipeline/audio_pipeline.py` — new `_find_ffmpeg()` helper:
```python
def _find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found: return found
    winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    matches = glob.glob(os.path.join(winget_base, "Gyan.FFmpeg*", "**", "ffmpeg.exe"), recursive=True)
    return matches[0] if matches else None
```
`plugins/telegram_bot/telegram_bot.py` — two ffmpeg call sites updated to use `_ap._find_ffmpeg()`.

#### Screenshot Pipeline — Web UI + Telegram
**Web UI:** `browser_screenshot` returns `{"image": "data:image/png;base64,..."}`. `aion.py` collects this into `collected_images` list, builds `response_blocks` with `{"type": "image", "url": "..."}`, sends in `done` event. Frontend appends `<img>` via `appendImageBlock()`.
**Telegram:** `response_blocks` are received from `stream()` and rendered. For images:
- `data:` URLs (base64) → decoded and sent as multipart file upload (`sendPhoto` with `files=`)
- HTTP URLs → sent directly as JSON `photo` field
**Previously broken:** Telegram was sending `data:` URLs as JSON strings → Telegram API rejected silently.

#### Channel-Filtered History Load
**Fix (commit b0504a9):** `load_history()` now uses `channel_filter="web"` in Web UI sessions. Heartbeat/Telegram messages no longer appear in Web UI chat after restart.

### 12. Bug Fixes (2026-03-22 — Session 3)

#### Multiple Telegram Workers (4 Responses per Message)
**Problem:** Module-level `_polling_started = False` gets reset each time the plugin module is re-imported (hot-reload). Every reload started a new polling thread → 4 active workers = 4 responses per message.
**Fix:** `plugins/telegram_bot/telegram_bot.py` — replaced `_polling_started` flag with `threading.enumerate()` check by thread name:
```python
def _start_polling(token: str):
    with _polling_lock:
        for t in threading.enumerate():
            if t.name == "telegram-polling" and t.is_alive():
                print("[Telegram] Polling-Thread läuft bereits — kein zweiter Start.")
                return
        t = threading.Thread(target=_run, daemon=True, name="telegram-polling")
        t.start()
```
`threading.enumerate()` survives module reloads — the thread object lives in the OS, not in the module namespace.
**Same fix applied to:** `discord_bot.py` (thread name `"discord-bot"`) and `slack_bot.py` (thread name `"slack-bot"`).

#### Telegram Spam — `send_telegram_message` During Conversation
**Problem:** AION called `send_telegram_message` tool mid-conversation to "send the response". This is wrong — the tool is for PROACTIVE outbound messages only. During an active session, the reply is sent automatically after `stream()` completes.
**Fix 1:** `prompts/rules.md` — added `=== TELEGRAM / MESSAGING TOOLS (CRITICAL) ===`:
- `send_telegram_message` = only for PROACTIVE notifications (scheduler, heartbeat, alerts)
- NEVER call it during an active conversation — the reply is sent automatically
**Fix 2:** `telegram_bot.py` — when `tg_tool_sent=True`, images and voice are still delivered:
```python
if tg_tool_sent:
    image_blocks = [b for b in response_blocks if b.get("type") == "image" and b.get("url")]
    for block in image_blocks:
        await _send_photo(chat_id, block["url"])
    if is_voice_input and response.strip():
        await _send_voice_reply(chat_id, response)
    continue
```

#### Infinite Error Loop Fix
**Problem:** When the asyncio event loop shut down, `await asyncio.sleep(5)` inside the error handler also raised an exception → infinite recursion loop spamming "cannot schedule new futures after shutdown" to the console.
**Fix:** `telegram_bot.py` — error handler detects shutdown signals and returns cleanly:
```python
except Exception as e:
    err_msg = str(e)
    if "shutdown" in err_msg or "futures after" in err_msg or "closed" in err_msg:
        print("[Telegram] Event-Loop beendet — Worker beendet sich sauber.")
        return
    try:
        await asyncio.sleep(5)
    except Exception:
        return  # sleep failed too → loop is gone, exit cleanly
```

#### `restart_with_approval` Rewrite
**Problem:** AION had broken `restart_tool.py` by adding `api.get_context("channel", default="web")` — this method does NOT exist in PluginAPI. Also introduced a circular import to `telegram_bot`. Plugin crashed on load.
**Fix:** Complete rewrite with simple `confirmed` parameter pattern:
```python
def restart_with_approval(reason: str = "", confirmed: bool = False, **_) -> dict:
    if not confirmed:
        return {
            "approval_required": True,
            "message": "AION-Prozess neu starten?" + (f" Grund: {reason}" if reason else ""),
            "preview": "Der aktuelle AION-Prozess wird beendet...\n→ 'Ja' zum Neustart, 'Nein' zum Abbrechen."
        }
    entry = _get_aion_entry_point()
    subprocess.Popen([sys.executable, str(entry)], creationflags=subprocess.CREATE_NEW_CONSOLE)
    os._exit(0)
```
**Rule:** PluginAPI does NOT have `get_context()`, `get_channel()`, or similar methods. Never call them.
**Also fixed:** `rules.md` — removed references to non-existent `start.bat`. AION is started via `python aion_web.py` or `aion` command.

#### Discord + Slack — Images and Voice
**Problem:** Discord and Slack bots used `sess.turn()` which does not return `response_blocks`. Images from `browser_screenshot` were never sent to these channels.
**Fix — Discord (`discord_bot.py`):**
- Switched to `sess.stream()` → reads `response_blocks` from `done` event
- `_send_image(channel, url)`: `data:` URLs decoded to bytes → `discord.File(io.BytesIO(...))`, HTTP URLs sent as text
- Voice input: audio attachment → transcribe via `audio_pipeline.audio_transcribe_any` → text
- Voice output: TTS via `audio_pipeline.audio_tts` → send as `discord.File`
- Slash command `/ask` also uses `response_blocks`

**Fix — Slack (`slack_bot.py`):**
- `_run_session` switched to `sess.stream()` with `response_blocks`
- Images: `data:` URLs → `files_upload_v2(content=img_bytes)` (fallback: `files_upload`), HTTP URLs → text message

#### Double `.mp3` Extension Bug
**Problem:** `_tts_edge()` in `audio_pipeline.py`:
```python
mp3_path = output_path.replace(".wav", ".mp3") if output_path.endswith(".wav") else output_path + ".mp3"
```
When `audio_tts` creates the temp file with `suffix=".mp3"` (edge engine) and passes the path, `_tts_edge` blindly appended `.mp3` again → `filename.mp3.mp3`. On Windows, the 8.3 short name truncated this to `filename.mp3.mp__3` — causing ffmpeg to fail on the file.
**Fix:**
```python
if output_path.endswith(".mp3"):
    mp3_path = output_path
elif output_path.endswith(".wav"):
    mp3_path = output_path.replace(".wav", ".mp3")
else:
    mp3_path = output_path + ".mp3"
```

#### Telegram Response Ordering — Voice at End
**Problem:** When `response_blocks` is non-empty (images present), the `elif is_voice_input` branch was never reached → voice reply never sent. User expected: text → image → text → image → voice.
**Fix:** Voice reply moved inside the `if response_blocks:` block, executed after all text/image blocks:
```python
if response_blocks:
    for block in blocks_to_send:
        # ... send text and images in order ...
    # Voice comes last — after all text and images
    if is_voice_input and response.strip() and not needs_approval:
        await _send_voice_reply(chat_id, response)
elif is_voice_input ...:
    # Only reached when no response_blocks at all
    sent = await _send_voice_reply(chat_id, response)
```

### 13. Claude CLI Provider Plugin + Audio Web UI + Keys Tab (2026-03-22 — Session 4)

#### Claude CLI Provider Plugin (`plugins/claude_cli_provider/claude_cli_provider.py`)
**What:** New plugin that connects AION to the user's Claude.ai subscription via the Claude Code CLI. No API key needed — uses `claude login` (OAuth).
**Tools registered:**
| Tool | Description |
|------|-------------|
| `ask_claude` | Send a task to Claude via `claude --print --model <model>`. Appends `context_files` content (max 30k chars each). Reads `task_routing` from `config.json` for default model. |
| `get_task_routing` | Show current routing config + whether claude CLI is available. |
| `set_task_routing` | Write `task_routing` to `config.json`. Use `"remove"` to delete an entry. |
| `claude_cli_login` | Install Claude Code CLI via npm if missing, then open browser for OAuth login. |
| `claude_cli_status` | Check if CLI is installed and authenticated. |

**Key internals:**
- `_find_claude()`: searches PATH → npm APPDATA → `~/.claude/local` → WinGet glob
- `_claude_authenticated()`: runs `claude --print --model claude-haiku-4-5-20251001 ping` with 10s timeout
- Task routing: `config.json → "task_routing"` maps task types to models. `ask_claude(task_type="coding")` picks the right model automatically.
- Default routing (set in onboarding): `coding → claude-opus-4-6`, `review → claude-sonnet-4-6`, `browsing → gemini-2.5-flash`, `default → gemini-2.5-pro`

**Rules added to `prompts/rules.md`:**
```
=== TASK ROUTING — CLAUDE FOR CODING ===
For all code-writing, refactoring, review, and algorithm tasks:
1. file_read() the relevant files
2. ask_claude(prompt, context_files=[...], task_type="coding")
3. Apply result via file_replace_lines() or file_write()
```

**IMPORTANT:** `PluginAPI` does NOT have `get_context()` — never call it. Use keyword args: `def fn(param: str = "", **_)`.

---

#### Audio in Web UI (`aion.py` + `aion_web.py` + `static/index.html`)
**What:** Audio generated by `audio_tts` is now visible in the Web UI as an `<audio>` player.

**Pipeline:**
1. `aion.py` — after `audio_tts` tool result: collect into `collected_audio` list (parallel to `collected_images`):
```python
if ok and fn_name == "audio_tts":
    audio_path = result_data.get("path", "")
    if audio_path and os.path.exists(audio_path):
        collected_audio.append({"path": audio_path, "format": result_data.get("format", "mp3")})
```
2. `aion.py` — build `response_blocks` entry: `{"type": "audio", "url": "/api/audio/<filename>", "format": ..., "path": ...}`
3. `aion_web.py` — `/api/audio/{filename}` endpoint: serves temp files from `tempfile.gettempdir()` with security checks (extension allowlist `.mp3/.wav/.ogg`, no path traversal)
4. `static/index.html` — `appendAudioBlock(url, format)`: renders `<audio controls src="...">` inside AION's message bubble. Done handler: checks `b.type === 'audio'` in `ev.response_blocks`

---

#### Web UI Keys Tab Improvements
**What:** Keys tab now shows provider-specific setup instructions, direct links, and status indicators.

**`_KEY_META` dict** in `static/index.html` provides per-provider:
- `label`: display name
- `hint`: short description of what the key is
- `link`: direct URL to get the key (AI Studio, OpenAI platform, Anthropic console, etc.)
- `isSubscription`: true for Claude (no API key)

**Visual additions:**
- Green/red status dots (key present = green, missing = red/orange)
- "Get Key ↗" links for API-key providers
- Claude Login block at top with `checkClaudeStatusInKeys()` + `claudeCliLoginFromKeys()` (auto-polls every 4s for 2 minutes after login initiated)

---

#### Task Routing in Web UI System Tab
**What:** New "Claude CLI / Task Routing" section in the System tab.

**Fields:** coding, review, browsing, default model inputs
**Status indicator:** Shows whether claude CLI is installed + authenticated
**`saveTaskRouting()`:** POSTs to `/api/config/settings` with `{task_routing: {...}}`
**Fix:** `/api/config/settings` `allowed` set now includes `"task_routing"` (previously missing → silently dropped)

---

#### New API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/audio/{filename}` | GET | Serve temp audio file (mp3/wav/ogg) with security checks |
| `/api/claude-cli/status` | GET | `{installed, authenticated, path}` — runs ping test |
| `/api/claude-cli/login` | POST | Install claude CLI if missing, then `Popen([claude_bin, "login"])` to open browser |

**`_find_claude_bin_web()`:** Shared helper in `aion_web.py` (same search logic as `_find_claude()` in plugin).

---

#### Onboarding — Claude CLI Setup (Step 8)
**What:** `onboarding.py` Step 8 (Advanced) now includes Claude CLI setup section.
- Checks if installed (`_find_claude_bin()`)
- Offers npm auto-install if missing
- Runs `claude login` subprocess
- Configures `task_routing` with sensible defaults or custom values
- Step 9 System Check shows Claude CLI status
- `completion_banner()` shows routing config

---

## Prior Improvements (2026-03-21 and earlier)

### Universal Provider Plugin Architecture
**Providers:** Gemini, OpenAI, DeepSeek, Anthropic (Claude), Grok, Ollama — all via plugin registry.

### Unsupported File Message Utility
**Single source of truth** for file type responses across all channels.

### edge-tts Activated
Microsoft Neural TTS for high-quality voice replies.

### Task-Completion Enforcer
Forces completion check if tasks are incomplete.

### Channel-Aware History
Telegram/Web/Heartbeat histories isolated by channel.

### Plugin Subdirectory Enforcement
Prevents broken plugin structures automatically.

---

### Files & Directories

```
AION/
├── aion.py                      # Core: _build_system_prompt, _dispatch, _build_tool_schemas, providers
├── aion_session.py              # AionSession class + stream() — the LLM turn loop (REFACTORED OUT of aion.py)
├── aion_memory.py               # AionMemory class — RAG memory, record, search (REFACTORED OUT of aion.py)
├── aion_web.py                  # Web server (FastAPI + SSE), port 7000
├── aion_cli.py                  # CLI mode: interactive terminal without browser/server
├── plugin_loader.py             # Loads plugins + register_router (_pending_routers)
├── static/index.html            # Web UI (Vanilla JS)
│                                  → Persistent sidebar (172px): 💬 Chat | 📝 Prompts
│                                    | 🔌 Plugins | 🧠 Memory | ⊞ System
│                                  → Thoughts/tool calls inline as accordions in chat
├── plugins/
│   ├── core_tools/              # continue_work, read_self_doc, read_plugin_doc, system_info, memory_record
│   ├── focus_manager/           # focus_set/get/clear (persistent task focus, injected every turn)
│   ├── reflection/              # reflect (inner monologue → thoughts.md, near-duplicate protection)
│   ├── character_manager/       # update_character (update character.md)
│   ├── shell_tools/             # shell_exec, winget_install, install_package
│   ├── web_tools/               # web_search, web_fetch
│   ├── pid_tool/                # get_own_pid
│   ├── restart_tool/            # restart_with_approval
│   ├── audio_pipeline/          # Universal audio: transcription (Faster Whisper) + TTS (edge-tts/sapi5)
│   ├── audio_transcriber/       # Audio transcription via Faster Whisper (offline, multilingual)
│   │   └── ~/.cache/huggingface/  # Whisper model cache (auto-downloaded)
│   ├── scheduler/               # Cron scheduler (schedule_add/list/remove/toggle)
│   │   └── tasks.json           # scheduled tasks (auto-generated)
│   ├── telegram_bot/            # Telegram bidirectional (text + images + voice messages)
│   ├── discord_bot/             # Discord bot (DMs + @mentions + slash command /ask)
│   ├── slack_bot/               # Slack bot (Socket Mode, DMs + @aion mentions)
│   ├── alexa_plugin/            # Amazon Alexa Skill endpoint (POST /api/alexa)
│   ├── playwright_browser/      # Browser automation (8 tools: open, screenshot, click, fill, get_text, evaluate, find, close)
│   ├── multi_agent/             # Multi-agent routing (delegate_to_agent, sessions_list, sessions_send, sessions_history)
│   ├── gemini_provider/         # Google Gemini provider (registers prefix "gemini")
│   ├── anthropic_provider/      # Anthropic Claude (registers prefix "claude")
│   ├── deepseek_provider/       # DeepSeek API (registers prefix "deepseek")
│   ├── grok_provider/           # xAI Grok (registers prefix "grok")
│   ├── ollama_provider/         # Local Ollama server (registers prefix "ollama/")
│   ├── memory_plugin/           # Conversation history (JSONL, channel-aware)
│   ├── clio_reflection/         # DISABLED (_clio_reflection.py — had fake random values)
│   ├── todo_tools/              # Task management
│   ├── smart_patch/             # Fuzzy code patching
│   ├── image_search/            # Image search (Openverse + Bing/Playwright)
│   ├── docx_tool/               # Create Word documents
│   ├── moltbook/                # Social platform moltbook.com
│   ├── claude_cli_provider/     # Claude.ai subscription via CLI (ask_claude, claude_cli_login, task routing)
│   └── heartbeat/               # Keep-alive + autonomous todo round every 30min
├── character.md                 # My personality (self-updating via update_character)
├── prompts/
│   └── rules.md                 # System prompt / behavioral rules (editable via Web UI Prompts tab)
├── aion_memory.json             # Persistent memory (max. 300 entries)
├── conversation_history.jsonl   # Full conversation history
├── thoughts.md                  # Recorded thoughts (reflect tool)
├── AION_SELF.md                 # This file (technical reference — on-demand via read_self_doc)
├── .env                         # API keys (not in Git)
└── config.json                  # Persistent settings (model, exchange_count)
```

---

## Core Architecture

### How a Turn Works (aion_session.py → AionSession.stream())

`AionSession` is the **per-channel conversation session** (one per channel: web, telegram_*, discord_*, ...).
Its `stream()` method is an async generator that yields event dicts:

```
{"type": "token",       "content": "..."}           — streamed text token
{"type": "thought",     "text": "...", "trigger": "..."} — internal thought (CLIO/reflection)
{"type": "tool_call",   "tool": "...", "args": {...}}
{"type": "tool_result", "tool": "...", "result": {...}, "ok": bool, "duration": 0.1}
{"type": "done",        "full_response": "...", "response_blocks": [...]}
{"type": "error",       "message": "..."}
{"type": "approval",    "message": "..."}           — desktop action needs confirmed=true
```

**Message assembly at turn start** (`aion_session.py`, start of `stream()`):
1. `memory.get_context_semantic(user_input)` → semantic memory injection
2. `_m._get_recent_thoughts(5)` → recent thoughts from thoughts.md
3. `_m._build_system_prompt(self.channel)` → full system prompt (cached per channel+model+tool-count)
4. Combine: `effective = sys_prompt + mem_ctx + thoughts_ctx`
5. Truncate history to `max_history_turns` (default 40) oldest messages
6. Append new user message

**Tool loop** (while True, max `MAX_TOOL_ITERATIONS=50`):
1. Call LLM API with `tools=_build_tool_schemas()` (tier-1 by default)
2. If model calls a tool → `await _m._dispatch(name, inputs)`
3. On "Unknown tool" error → auto-escalate: `tools = _build_tool_schemas(tier_threshold=2)`
4. After desktop actions → auto-screenshot injected as user message for visual feedback
5. Completion-check after text response — if model announced action without calling tool → retry
6. Task-check after tools called — if task incomplete → retry
7. Break when model produces final text with no pending actions

**To inject additional context into every turn** → modify `aion_session.py` around the
`effective = sys_prompt + mem_ctx + thoughts_ctx` block (lines ~108-115), OR add to
`_build_system_prompt()` in `aion.py` (but that is cached — avoid for dynamic state).
For dynamic per-turn injection (e.g. focus state): append to `messages` after assembly.

---

### _build_system_prompt() — aion.py

```python
def _build_system_prompt(channel: str = "") -> str
```
- **Cache key**: `(channel, MODEL, len(_plugin_tools))` — invalidated when tools change
- Loads `character.md`, `prompts/rules.md` (max 12,000 chars)
- Placeholders: `{CHARAKTER}`, `{MODEL}`, `{BOT_AION}`, `{BOT_MEMORY}`, `{BOT_PLUGINS}`, `{BOT_SELF}`
- Appends: plugin overview block + thinking prompt + mood/temporal/relationship hints
- **NOT suitable for dynamic per-turn data** (result is cached)

---

### _dispatch() — aion.py

```python
async def _dispatch(name: str, inputs: dict, _bypass_retry: bool = False) -> str
```
Returns a **JSON string** always. Built-in handlers first, then plugin tools, then:
- Dot-notation normalization: `desktop.hotkey` → `desktop_hotkey`, `core_tools.info` → `info`
- Returns `{"error": "Unknown tool: <name>"}` if nothing matches

**Built-in tools handled directly in _dispatch:**
`file_read`, `file_write`, `self_read_code`, `self_patch_code`, `file_replace_lines`,
`file_list`, `memory_add`, `memory_search`, `memory_read_history`, `memory_append_history`,
`memory_compress`, `read_self_doc`, `generate_self_doc_summary`, `set_thinking_level`,
`set_channel_allowlist`, `get_control_settings`, `list_tools`

---

### _build_tool_schemas() — aion.py

```python
def _build_tool_schemas(tier_threshold: int = 0) -> list[dict]
```
- `tier_threshold=0` → use `config.json["tool_tier"]` (default 1)
- `tier_threshold=1` → tier-1 tools only
- `tier_threshold=2` → tier-1 + tier-2 (all tools)
- Called with `tier_threshold=2` by `aion_session.py` on auto-escalation

**Tier-2 plugins** (excluded by default): `desktop`, `playwright_browser`, `telegram_bot`,
`discord_bot`, `slack_bot`, `multi_agent`, `audio_pipeline`, `audio_transcriber`,
`image_search`, `moltbook`, `docx_tool`, `mood_engine`, `proactive`, `mcp_client`, `paperless`

---

### AionMemory — aion_memory.py

```python
memory = AionMemory(MEMORY_FILE, VECTORS_FILE, max_entries=300)
```
- `memory.record(category, summary, lesson, success, error, hint)` — write insight
- `memory.get_context_semantic(query, max_entries=3)` → RAG search via Ollama embeddings (top 3 injected per turn)
- `memory.get_context(query, max_entries=8)` → keyword fallback
- Embeddings cached in `aion_memory_vectors.json`, threshold cosine > 0.35

---

## Plugin Tools (complete list)

### Core Tools (`core_tools.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `continue_work` | `next_step: str` | Signals continued work without waiting for the user. Use after EVERY tool result when more steps follow. |
| `read_self_doc` | `full: bool` | Reads AION_SELF.md — the technical self-documentation. Default: compressed summary. |
| `read_plugin_doc` | `plugin: str` | Read the full README for a plugin. Call without args to list all documented plugins. |
| `system_info` | — | Platform, Python version, loaded tools, model, character_file. |
| `memory_record` | `category: str`, `summary: str`, `lesson: str`, `success: bool` | Write an insight to memory. Categories: `capability`, `user_preference`, `self_improvement`, `tool_failure`, `conversation`. |

### Reflection & Character
| Tool | Parameters | Description |
|------|-----------|-------------|
| `reflect` | `thought: str`, `trigger: str` | Write inner thoughts → `thoughts.md`. AFTER experiences only — not for plans. Near-duplicates (>55% word overlap) are auto-skipped. Triggers: `general`, `error`, `insight`, `user_observation`, `task_completed`, `uncertainty`. |
| `update_character` | `section: str`, `content: str`, `reason: str` | Updates `character.md`. Sections: `user`, `insights`, `improvements`, `presence`, `humor`, `quirks`, `personality`. USE OFTEN! |

### Focus Manager (`focus_manager.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `focus_set` | `task: str` | Set the current task focus. Injected into every turn's system prompt until cleared. |
| `focus_get` | — | Read the currently active focus. |
| `focus_clear` | — | Clear the focus when the task is fully done. |

> **focus_manager** prevents topic drift on multi-step tasks. The active focus is stored in
> `plugins/focus_manager/focus_state.json` and re-injected every turn via `aion_session.py`.

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
| `list_tools` | `filter: str` (optional) | List all registered tools (tier-1 + tier-2) with names, tiers, descriptions. Use before attempting a task — never invent tool names. |
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

### Discord (`discord_bot.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `send_discord_message` | `message: str` | Send a message to the Discord user (requires active session). |

**Features:**
- Per-user sessions (DMs + @mentions)
- Slash command `/ask` for explicit requests
- Auto-splits messages at 1900 chars (Discord limit 2000)
- Requires `DISCORD_BOT_TOKEN` in `.env`
- Requires `MESSAGE CONTENT INTENT` enabled in Discord Developer Portal

### Slack (`slack_bot.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `send_slack_message` | `message: str` | Send a message to the Slack user (requires active session). |

**Features:**
- Socket Mode via slack-bolt
- Responds to `@aion` mentions + DMs
- Per-user sessions (`slack_{user_id}` channel)
- Requires `SLACK_BOT_TOKEN` (xoxb-) + `SLACK_APP_TOKEN` (xapp-) in `.env`
- Async wrapper uses `asyncio.new_event_loop()` for each message

### Browser Automation (`playwright_browser.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `browser_open` | `url: str`, `headless?: bool` | Open a browser to a URL. |
| `browser_screenshot` | `selector?: str` | Take a screenshot (full page or specific element). |
| `browser_click` | `selector: str` | Click an element by CSS selector. |
| `browser_fill` | `selector: str`, `value: str` | Fill an input/textarea/select element. |
| `browser_get_text` | `selector: str` | Extract text from an element. |
| `browser_evaluate` | `expression: str` | Execute JavaScript and return result. |
| `browser_find` | `query: str` | Natural language element search. |
| `browser_close` | — | Close the browser. |

**Features:**
- Thread-safe singleton via `threading.Lock`
- Configurable headless mode via `config.json: "browser_headless"` (default: true)
- Auto-installed in onboarding Step 9
- Graceful fallback if Playwright not available

### Multi-Agent Routing (`multi_agent.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `delegate_to_agent` | `prompt: str`, `steps: int`, `debug?: bool` | Delegate a task to a new sub-agent. Returns result + summary. |
| `sessions_list` | — | List all active sub-agent sessions (ID, status, steps used). |
| `sessions_send` | `session_id: str`, `message: str` | Send a message to a specific sub-agent. |
| `sessions_history` | `session_id?: str` | Read conversation history of a sub-agent (or all sessions). |

**Features:**
- Sub-agent IDs: `subagent_{uuid8}` format
- Recursion guard: checks `_active_channel` prefix to prevent infinite loops
- Independent sessions with isolated memory
- Useful for parallel complex tasks or specialized workflows

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
| `audio_transcribe_any` | `file_path: str`, `language?: str` | Any audio file (ogg, mp3, m4a, wav, flac, webm, ...) → text. Uses Faster Whisper (offline, multilingual, auto-detects language). Auto-converts non-WAV via ffmpeg if needed. |
| `audio_tts` | `text: str`, `engine?: str`, `output_path?: str` | Text → speech file. Engines: `edge` (Microsoft Neural, online, best quality), `sapi5` (offline fallback). Config via `config.json: tts_engine + tts_voice`. |

### Claude CLI Provider (`claude_cli_provider.py`)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `ask_claude` | `prompt: str`, `model?: str`, `context_files?: list`, `task_type?: str` | Send task to Claude via `claude --print`. Reads `task_routing` for default model. `context_files` content is appended (max 30k chars each). |
| `claude_cli_login` | — | Install Claude Code CLI via npm if missing, then open browser for OAuth login. |
| `claude_cli_status` | — | Check if CLI is installed and authenticated. |
| `get_task_routing` | — | Show current task routing config + whether CLI is available. |
| `set_task_routing` | `coding?: str`, `browsing?: str`, `default?: str` | Update `task_routing` in `config.json`. Use `"remove"` to delete an entry. |

**When to use `ask_claude`:** For all code writing, refactoring, review, algorithm, and architecture tasks. Do NOT use for web browsing or simple queries.
**Workflow:** `file_read()` → `ask_claude(prompt, context_files=[...])` → `file_replace_lines()` or `file_write()`.

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
| POST | `/api/config/settings` | Update system settings (TTS engine/voice, model_fallback, browser_headless) |
| GET | `/api/oauth/google/start` | Begin Google OAuth flow for Gemini subscription |
| GET | `/api/oauth/google/callback` | OAuth callback handler (returns auth token) |
| POST | `/api/alexa` | Amazon Alexa Skill endpoint (alexa_plugin) |

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
- **📝 Prompts**: `prompts/rules.md`, `character.md`, `AION_SELF.md` — full width, instantly saveable
- **🔌 Plugins**: all plugins + tools (✓/✗) + hot-reload
- **🧠 Memory**: searchable entries (green/red), deletable
- **⊞ System**: statistics, model switching, paths, actions

## CLI Mode (`aion_cli.py`)

Alternative entry point without web server or browser.

```
aion --cli              # via installed command (recommended)
python aion_cli.py      # directly
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

4. **Code changes**: ALWAYS explain WHY the change is needed before proposing it. Show the diff and ask for confirmation. NEVER call a code-editing tool without first explaining the reasoning in plain text.

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

## Security & Control Features (2026-03-23)

### Channel Allowlist
**Purpose:** Restrict bot access to specific channels (e.g., allow only Telegram, block Discord/Slack).

**Configuration Methods:**

1. **Direct Config** (`config.json`):
```json
{
  "channel_allowlist": ["default", "web", "telegram*"]
}
```

2. **CLI Tool** (available immediately):
- `set_channel_allowlist(channels)` — Update allowlist dynamically
  - Example: `set_channel_allowlist(["default", "telegram*"])` → Only allow these
  - Example: `set_channel_allowlist([])` → Allow all channels (clear allowlist)
- `get_control_settings()` — Check current configuration

3. **WebUI** (planned): System tab will show Allowlist controls

**Behavior:**
- If `channel_allowlist` not set: all channels allowed (default)
- If set: only channels matching the list are permitted
- Supports wildcards: `"telegram*"` matches `telegram_123`, `telegram_456`, etc.
- Exact match: `"default"`, `"web"` match exactly
- Denied channels get error: `{"type": "error", "message": "Channel '...' ist nicht auf der Allowlist"}`

**Where it's checked:** `AionSession.stream()` at the beginning — before any processing.

### Thinking Level Control
**Purpose:** Adjust how deeply AION thinks before acting (helps with accuracy vs. speed tradeoff).

**Configuration Methods:**

1. **Direct Config** (`config.json`):
```json
{
  "thinking_level": "standard",
  "thinking_overrides": {
    "telegram*": "deep",
    "discord*": "minimal"
  }
}
```

2. **CLI Tools** (available immediately):
- `set_thinking_level(level, channel_override)` — Set global or per-channel
  - Example: `set_thinking_level("deep", "telegram*")` → Deep thinking for Telegram only
  - Example: `set_thinking_level("standard")` → Set global to standard
  - Levels: `"minimal"`, `"standard"`, `"deep"`, `"ultra"`
- `get_control_settings()` — Check current configuration (both allowlist + thinking level)

3. **WebUI** (planned): System tab will show Thinking Level + Allowlist controls

**Levels:**
| Level | Behavior |
|-------|----------|
| `minimal` | No extra reflection prompts; fast responses |
| `standard` | Use `reflect()` tool for complex decisions (default) |
| `deep` | Extensive thinking before each tool call; consider multiple approaches |
| `ultra` | Maximum reflection; every decision is deeply analyzed |

**Implementation:** Added to system prompt via `_get_thinking_prompt(channel)` — channel-specific overrides take precedence.

---

*Last updated: 2026-03-23 — Session 3: Channel allowlist security; Thinking level control; Phase 3 complete. Session 2: Browser hallucination prevention; Approval buttons; ffmpeg fallback; Screenshot fixes. Session 1: Playwright browser automation; Dynamic model failover; Discord + Slack bots; Multi-agent routing; Docker; Google OAuth; Onboarding; Web UI redesign*
