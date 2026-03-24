#!/usr/bin/env python3
"""
AION Onboarding — First-run Setup Wizard.
Automatically called on first start.
"""
import os
import sys
import json
import re

# UTF-8 + ANSI/VT100 on Windows
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 0x0007)
    except Exception:
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path

BOT_DIR = Path(__file__).parent

# ── ANSI Colors ───────────────────────────────────────────────────────────────
_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text

C_CYAN   = "96"
C_BOLD   = "1"
C_GREEN  = "92"
C_YELLOW = "93"
C_RED    = "91"
C_DIM    = "90"
C_WHITE  = "97"
C_LOGO   = "96;1"

# ── Helpers ───────────────────────────────────────────────────────────────────

def ok(msg: str) -> None:
    print(f"  {_c(C_GREEN, '[OK]')}  {msg}")

def warn(msg: str) -> None:
    print(f"  {_c(C_YELLOW, '[!]')}   {msg}")

def err(msg: str) -> None:
    print(f"  {_c(C_RED, '[X]')}  {msg}")

def info(msg: str) -> None:
    print(f"  {_c(C_DIM, '...')}  {msg}")

def ask(prompt: str, default: str = "") -> str:
    hint = f" [{_c(C_DIM, default)}]" if default else ""
    try:
        val = input(f"  {_c(C_CYAN, prompt)}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise
    return val if val else default

def ask_hidden(prompt: str) -> str:
    print(f"  {_c(C_DIM, '(input is visible — normal for a setup wizard)')}")
    return ask(prompt)


def _select(items: list, default: int = 0) -> int:
    """Interactive arrow-key selector. Returns selected index.
    Use ↑/↓ to navigate, Enter to confirm.
    Falls back to numbered input when stdout is not a TTY."""
    n   = len(items)
    idx = max(0, min(default, n - 1))

    def _render(sel: int) -> None:
        for i, item in enumerate(items):
            if i == sel:
                print(f"  {_c('92;1', '>')} {_c('97;1', item)}")
            else:
                print(f"    {_c(C_DIM, item)}")
        sys.stdout.flush()

    def _erase(count: int) -> None:
        sys.stdout.write(f"\x1b[{count}A\x1b[J")
        sys.stdout.flush()

    if not _TTY:
        # Non-interactive fallback
        for i, item in enumerate(items, 1):
            marker = _c(C_GREEN, "*") if i - 1 == default else " "
            print(f"  {marker} {_c(C_WHITE, str(i))}  {item}")
        print()
        while True:
            val = ask(f"Choice (1-{n})", str(default + 1))
            if val.isdigit() and 1 <= int(val) <= n:
                return int(val) - 1
            warn(f"Enter a number between 1 and {n}.")

    print(f"  {_c(C_DIM, 'Arrow keys ↑↓  ·  Enter to select')}")
    _render(idx)

    try:
        if sys.platform == "win32":
            import msvcrt
            while True:
                key = msvcrt.getch()
                if key in (b'\r', b'\n'):
                    break
                if key in (b'\x00', b'\xe0'):
                    k2 = msvcrt.getch()
                    if k2 == b'H':        # Up
                        idx = (idx - 1) % n
                    elif k2 == b'P':      # Down
                        idx = (idx + 1) % n
                elif key == b'\x1b':
                    raise KeyboardInterrupt
                _erase(n)
                _render(idx)
        else:
            import tty, termios
            fd  = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    if ch in ('\r', '\n'):
                        break
                    if ch == '\x1b':
                        seq = sys.stdin.read(2)
                        if seq == '[A':
                            idx = (idx - 1) % n
                        elif seq == '[B':
                            idx = (idx + 1) % n
                    elif ch == '\x03':
                        raise KeyboardInterrupt
                    _erase(n)
                    _render(idx)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass  # keep last idx

    _erase(n)
    print(f"  {_c(C_GREEN, '>')} {_c('97;1', items[idx])}")
    return idx


def section(title: str, step: str) -> None:
    print()
    print(f"  {_c(C_LOGO, '====================================================')} ")
    print(f"  {_c(C_BOLD, step)}  {_c(C_WHITE, title)}")
    print(f"  {_c(C_LOGO, '====================================================')} ")
    print()

# ── Provider & Model Registry ─────────────────────────────────────────────────

PROVIDERS = {
    "gemini": {
        "label":    "Google Gemini",
        "note":     "Free tier available · fast · recommended",
        "key_env":  "GEMINI_API_KEY",
        "key_url":  "https://aistudio.google.com/app/apikey",
        "key_fmt":  "AIza",
        "key_hint": "Format: AIza...",
        "models": [
            ("gemini-2.5-pro",           "Best quality  · deep reasoning  · slow"),
            ("gemini-2.5-flash",         "Fast & affordable  (recommended)"),
            ("gemini-2.5-flash-lite",    "Ultra-fast  · minimal cost"),
            ("gemini-2.0-flash",         "Stable & reliable"),
        ],
        "default_model": "gemini-2.5-flash",
    },
    "openai": {
        "label":    "OpenAI",
        "note":     "GPT-4.1, o3, o4-mini ...",
        "key_env":  "OPENAI_API_KEY",
        "key_url":  "https://platform.openai.com/api-keys",
        "key_fmt":  "sk-",
        "key_hint": "Format: sk-...",
        "models": [
            ("gpt-4.1",      "OpenAI flagship  · best quality"),
            ("gpt-4.1-mini", "Faster GPT-4.1  · affordable"),
            ("gpt-4o",       "Multimodal  · images & audio"),
            ("o3",           "Deep reasoning  · slow & expensive"),
            ("o4-mini",      "Fast reasoning  · affordable  (recommended)"),
            ("gpt-4o-mini",  "Ultra-fast  · minimal cost"),
        ],
        "default_model": "o4-mini",
    },
    "deepseek": {
        "label":    "DeepSeek",
        "note":     "Very fast · very cheap · strong reasoning",
        "key_env":  "DEEPSEEK_API_KEY",
        "key_url":  "https://platform.deepseek.com",
        "key_fmt":  "sk-",
        "key_hint": "Format: sk-...",
        "models": [
            ("deepseek-chat",     "DeepSeek V3 · best for general tasks"),
            ("deepseek-reasoner", "DeepSeek R1 · math / code / reasoning"),
        ],
        "default_model": "deepseek-chat",
    },
    "anthropic": {
        "label":    "Anthropic (Claude)",
        "note":     "Claude Sonnet/Opus/Haiku · strong coding",
        "key_env":  "ANTHROPIC_API_KEY",
        "key_url":  "https://console.anthropic.com/settings/keys",
        "key_fmt":  "sk-ant-",
        "key_hint": "Format: sk-ant-...",
        "models": [
            ("claude-opus-4-6",           "Most capable  · slow · expensive"),
            ("claude-sonnet-4-6",         "Best balance  · fast  (recommended)"),
            ("claude-haiku-4-5-20251001", "Fastest  · cheapest"),
            ("claude-3-5-sonnet-20241022","Claude 3.5 Sonnet (stable)"),
        ],
        "default_model": "claude-sonnet-4-6",
    },
    "grok": {
        "label":    "xAI Grok",
        "note":     "Grok 3 · real-time knowledge",
        "key_env":  "XAI_API_KEY",
        "key_url":  "https://console.x.ai",
        "key_fmt":  "xai-",
        "key_hint": "Format: xai-...",
        "models": [
            ("grok-3",      "Grok 3 flagship"),
            ("grok-3-mini", "Grok 3 Mini · fast & cheap"),
            ("grok-2",      "Grok 2 (previous gen)"),
        ],
        "default_model": "grok-3",
    },
    "ollama": {
        "label":    "Ollama (local)",
        "note":     "100% offline · no API key · any model",
        "key_env":  None,
        "key_url":  "https://ollama.com/download",
        "key_fmt":  None,
        "key_hint": "No API key needed",
        "models": [
            ("ollama/llama3.2",       "Meta Llama 3.2 · 3B · fast"),
            ("ollama/llama3.1:8b",    "Meta Llama 3.1 · 8B · good quality"),
            ("ollama/qwen2.5",        "Alibaba Qwen 2.5 · strong multilingual"),
            ("ollama/deepseek-r1:8b", "DeepSeek R1 distilled · reasoning"),
            ("ollama/mistral",        "Mistral 7B"),
            ("ollama/phi4",           "Microsoft Phi-4"),
            ("ollama/gemma3",         "Google Gemma 3"),
            ("ollama/codellama",      "Meta Code Llama · coding"),
        ],
        "default_model": "ollama/llama3.2",
    },
}

# ── Banner ────────────────────────────────────────────────────────────────────

def banner() -> None:
    print()
    print(_c(C_LOGO, "  ===================================================="))
    print(_c(C_LOGO, "  =                                                  ="))
    print(_c(C_LOGO, "  =   AION  --  First Start: Setup                   ="))
    print(_c(C_LOGO, "  =                                                  ="))
    print(_c(C_LOGO, "  ===================================================="))
    print()
    print(f"  {_c(C_WHITE, 'Welcome! This wizard sets up AION once.')}")
    print(f"  {_c(C_DIM, 'All settings can be changed later in .env and config.json.')}")
    print()

# ── Step 1: Primary Provider ──────────────────────────────────────────────────

def step1_provider() -> str:
    section("Choose your primary AI provider", "Step 1/9:")
    print(f"  {_c(C_DIM, 'This will be the default model. You can add more providers in step 2.')}")
    print()

    provider_list = list(PROVIDERS.keys())
    items = []
    for pid in provider_list:
        p = PROVIDERS[pid]
        key_note = "  (no key needed)" if not p["key_env"] else ""
        items.append(f"{p['label']:<22}  {p['note']}{key_note}")

    idx = _select(items, default=0)
    ok(f"Provider: {PROVIDERS[provider_list[idx]]['label']}")
    return provider_list[idx]

# ── Step 2: Primary API Key ───────────────────────────────────────────────────

def _ask_api_key(provider_id: str) -> str:
    p = PROVIDERS[provider_id]
    if not p["key_env"]:
        # Ollama: no key needed
        info(f"Ollama uses local models — no API key required.")
        info(f"Install from: {p['key_url']}")
        info(f"Then run: ollama pull llama3.2")
        return "ollama"

    print(f"  {_c(C_DIM, 'Create key at:')}")
    print(f"  {_c(C_CYAN, p['key_url'])}")
    print(f"  {_c(C_DIM, p['key_hint'])}")
    print()

    while True:
        api_key = ask_hidden(f"API key for {p['label']}")
        if not api_key:
            warn("API key cannot be empty.")
            continue
        if p["key_fmt"] and not api_key.startswith(p["key_fmt"]):
            warn(f"Key does not start with '{p['key_fmt']}' — are you sure?")
            confirm = ask("Use anyway? (y/n)", "y")
            if confirm.lower() == "n":
                continue
        return api_key

def step2_apikey(provider: str) -> str:
    section(f"API key for {PROVIDERS[provider]['label']}", "Step 2/9:")
    return _ask_api_key(provider)

# ── Step 3: Model ─────────────────────────────────────────────────────────────

def step3_model(provider: str) -> str:
    section("Choose a model", "Step 3/9:")
    p = PROVIDERS[provider]
    model_list    = p["models"]
    default_model = p["default_model"]

    print(f"  {_c(C_DIM, 'Available models for')} {_c(C_CYAN, p['label'])}:")
    print()

    default_idx = next(
        (i for i, (n, _) in enumerate(model_list) if n == default_model), 0
    )
    items = [f"{name:<40}  {desc}" for name, desc in model_list]
    idx = _select(items, default=default_idx)
    chosen = model_list[idx][0]
    ok(f"Model: {chosen}")
    return chosen

# ── Step 4: Additional Providers ─────────────────────────────────────────────

def step4_additional_providers(primary: str) -> dict:
    section("Additional providers (optional)", "Step 4/9:")
    print(f"  {_c(C_DIM, 'Add more providers so AION can switch models on demand.')}")
    print(f"  {_c(C_DIM, 'Each provider is only active when its key is present in .env.')}")
    print()

    extra_keys: dict = {}
    remaining = [pid for pid in PROVIDERS if pid != primary]

    for pid in remaining:
        p = PROVIDERS[pid]
        label    = _c(C_CYAN, p["label"])
        note     = _c(C_DIM, p["note"])
        key_note = _c(C_DIM, "(no key needed)") if not p["key_env"] else ""
        ans = ask(f"Set up {label}  {note}  {key_note}? (y/n)", "n")
        if ans.lower() == "y":
            if not p["key_env"]:
                # Ollama
                info(f"Install: {p['key_url']}")
                info("Then run: ollama pull llama3.2")
                ok(f"{p['label']} enabled (no key needed)")
            else:
                print()
                key = _ask_api_key(pid)
                if key:
                    extra_keys[p["key_env"]] = key
                    ok(f"{p['label']} key saved.")
        print()

    return extra_keys

# ── Step 5: Messaging Channels ────────────────────────────────────────────────

def step5_channels() -> dict:
    section("Messaging channels (optional)", "Step 5/9:")
    print(f"  {_c(C_DIM, 'Connect AION to messaging platforms — each is a separate plugin.')}")
    print(f"  {_c(C_DIM, 'All channels are optional. You can add them later via .env.')}")
    print()

    result: dict = {}

    # ── Telegram ────────────────────────────────────────────────────────────
    print(f"  {_c(C_CYAN, 'Telegram')}")
    print(f"  {_c(C_DIM, 'Bidirectional bot — text, images, voice messages')}")
    use_tg = ask("Set up Telegram? (y/n)", "n")
    if use_tg.lower() == "y":
        print()
        print(f"  {_c(C_DIM, '1. Create a bot via @BotFather on Telegram → copy token')}")
        print(f"  {_c(C_DIM, '2. Get Chat ID: open https://api.telegram.org/bot<TOKEN>/getUpdates')}")
        print()
        token   = ask("Bot token (e.g. 123456:ABC-...)")
        chat_id = ask("Chat ID (e.g. 123456789)")
        if token and chat_id:
            result["TELEGRAM_BOT_TOKEN"] = token
            result["TELEGRAM_CHAT_ID"]   = chat_id
            ok("Telegram configured.")
        else:
            warn("Token or Chat ID missing — Telegram skipped.")
    else:
        info("Telegram skipped.")
    print()

    # ── Discord ─────────────────────────────────────────────────────────────
    print(f"  {_c(C_CYAN, 'Discord')}")
    print(f"  {_c(C_DIM, 'Bot responds to @Mentions and DMs — slash command /ask')}")
    use_dc = ask("Set up Discord? (y/n)", "n")
    if use_dc.lower() == "y":
        print()
        print(f"  {_c(C_DIM, '1. discord.com/developers/applications → New App → Bot')}")
        print(f"  {_c(C_DIM, '2. Copy Bot Token')}")
        print(f"  {_c(C_DIM, '3. Enable \"Message Content Intent\" under Bot → Privileged Gateway Intents')}")
        print()
        dc_token = ask("Discord Bot Token")
        if dc_token:
            result["DISCORD_BOT_TOKEN"] = dc_token
            ok("Discord configured.")
        else:
            warn("No token entered — Discord skipped.")
    else:
        info("Discord skipped.")
    print()

    # ── Slack ────────────────────────────────────────────────────────────────
    print(f"  {_c(C_CYAN, 'Slack')}")
    print(f"  {_c(C_DIM, 'Bot responds to @Mentions and direct messages via Socket Mode')}")
    use_sl = ask("Set up Slack? (y/n)", "n")
    if use_sl.lower() == "y":
        print()
        print(f"  {_c(C_DIM, '1. api.slack.com/apps → New App → From scratch')}")
        print(f"  {_c(C_DIM, '2. Enable Socket Mode → generate App-Level Token (scope: connections:write)')}")
        print(f"  {_c(C_DIM, '3. OAuth & Permissions → Bot scopes: app_mentions:read, chat:write, im:history, im:read, im:write')}")
        print(f"  {_c(C_DIM, '4. Install app → copy Bot User OAuth Token')}")
        print()
        sl_bot_token = ask("Slack Bot Token (xoxb-...)")
        sl_app_token = ask("Slack App Token (xapp-...)")
        if sl_bot_token and sl_app_token:
            result["SLACK_BOT_TOKEN"] = sl_bot_token
            result["SLACK_APP_TOKEN"] = sl_app_token
            ok("Slack configured.")
        else:
            warn("Token(s) missing — Slack skipped.")
    else:
        info("Slack skipped.")
    print()

    return result

# ── Step 6: Profile ───────────────────────────────────────────────────────────

def step6_profile() -> dict:
    section("Your profile", "Step 6/9:")
    print(f"  {_c(C_DIM, 'Helps AION adapt to you from day one.')}")
    print()

    name = ask("Your name", "")

    print()
    print(f"  {_c(C_DIM, 'Address:')}")
    anrede = ["informal", "formal"][_select(["informal  (you)", "formal  (Sir/Ma'am)"], default=0)]

    print()
    print(f"  {_c(C_DIM, 'Primary language:')}")
    lang = ["German", "English", "mixed"][_select(["German", "English", "mixed"], default=0)]

    print()
    print(f"  {_c(C_DIM, 'Primary use (comma-separated, e.g. \"1,3\"):')}")
    print(f"    {_c(C_WHITE, '1')}  Coding")
    print(f"    {_c(C_WHITE, '2')}  Research")
    print(f"    {_c(C_WHITE, '3')}  Productivity")
    print(f"    {_c(C_WHITE, '4')}  Creative writing")
    print(f"    {_c(C_WHITE, '5')}  General")
    use_map = {"1": "Coding", "2": "Research", "3": "Productivity",
               "4": "Creative writing", "5": "General"}
    use_input = ask("Selection (e.g. 1,3)", "5")
    uses = [use_map[p.strip()] for p in use_input.split(",") if p.strip() in use_map] or ["General"]

    print()
    print(f"  {_c(C_DIM, 'Response style:')}")
    style = ["Short & concise", "Normal", "Detailed"][_select(
        ["Short & concise", "Normal", "Detailed"], default=1
    )]

    print()
    extra = ask("Anything AION should know from the start? (optional, Enter = skip)", "")

    return {"name": name, "anrede": anrede, "lang": lang,
            "uses": uses, "style": style, "extra": extra}

# ── Step 7: Permissions ───────────────────────────────────────────────────────

_PERM_PRESETS = {
    "conservative": {
        "shell_exec": "ask", "install_package": "ask", "file_write": "ask",
        "file_delete": "ask", "self_modify": "ask",   "create_plugin": "ask",
        "restart": "ask",    "web_search": "allow",   "web_fetch": "allow",
        "telegram_auto": "ask", "memory_write": "allow", "schedule": "ask",
    },
    "balanced": {
        "shell_exec": "ask", "install_package": "ask", "file_write": "allow",
        "file_delete": "ask", "self_modify": "ask",   "create_plugin": "ask",
        "restart": "ask",    "web_search": "allow",   "web_fetch": "allow",
        "telegram_auto": "allow", "memory_write": "allow", "schedule": "ask",
    },
    "autonomous": {
        "shell_exec": "allow", "install_package": "allow", "file_write": "allow",
        "file_delete": "allow", "self_modify": "allow", "create_plugin": "allow",
        "restart": "allow",  "web_search": "allow",   "web_fetch": "allow",
        "telegram_auto": "allow", "memory_write": "allow", "schedule": "allow",
    },
}

_PERM_LABELS = {
    "shell_exec":      "Shell commands",
    "install_package": "Install packages (pip)",
    "file_write":      "Write / modify files",
    "file_delete":     "Delete files",
    "self_modify":     "Modify own code",
    "create_plugin":   "Create plugins",
    "restart":         "Restart AION",
    "web_search":      "Web search",
    "web_fetch":       "Fetch URLs",
    "telegram_auto":   "Send Telegram messages autonomously",
    "memory_write":    "Write to memory",
    "schedule":        "Create scheduled tasks",
}

def step7_permissions() -> dict:
    section("Permissions — what AION may do autonomously", "Step 7/9:")
    print(f"  {_c(C_DIM, 'Controls what AION does without asking you first.')}")
    print()
    preset_name = ["conservative", "balanced", "autonomous"][_select([
        "Conservative  — asks before anything that touches the system",
        "Balanced      — search/read/write free, shell/install needs OK  (recommended)",
        "Autonomous    — AION decides everything on its own",
    ], default=1)]
    perms = dict(_PERM_PRESETS[preset_name])
    ok(f"Preset '{preset_name}' selected.")
    print()

    customize = ask("Customize individual permissions? (y/n)", "n")
    if customize.lower() == "y":
        print()
        for key, label in _PERM_LABELS.items():
            current = perms[key]
            current_display = _c(C_GREEN, "allow") if current == "allow" else \
                              _c(C_YELLOW, "ask")  if current == "ask"   else \
                              _c(C_RED, "deny")
            val = ask(f"  {label:<42} [{current_display}]  (allow/ask/deny)", current).lower()
            if val in ("allow", "ask", "deny"):
                perms[key] = val
        print()

    perms["preset"] = preset_name
    return perms


# ── Step 8: Advanced Settings ─────────────────────────────────────────────────

def _find_claude_bin() -> str | None:
    """Sucht die claude CLI (für Onboarding-Check)."""
    import glob as _glob
    import shutil as _shutil
    found = _shutil.which("claude")
    if found:
        return found
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd"),
        os.path.join(os.environ.get("APPDATA", ""), "npm", "claude"),
        os.path.join(home, ".claude", "local", "claude.exe"),
        os.path.join(home, ".claude", "local", "claude"),
        *_glob.glob(
            os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         "Microsoft", "WinGet", "Packages",
                         "Anthropic.Claude*", "**", "claude.exe"),
            recursive=True,
        ),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _claude_cli_logged_in(claude_bin: str) -> bool:
    """Prüft ob claude CLI angemeldet ist (schneller Test-Aufruf)."""
    import subprocess as _sp
    try:
        r = _sp.run(
            [claude_bin, "--print", "--model", "claude-haiku-4-5-20251001", "ping"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
        return r.returncode == 0
    except Exception:
        return False


def step8_advanced() -> dict:
    section("Advanced settings", "Step 8/9:")
    print(f"  {_c(C_DIM, 'Fine-tune AION behavior. All settings can be changed later.')}")
    print()

    result: dict = {}

    # Port
    port = ask("Web UI port", "7000")
    result["port"] = port if port.isdigit() else "7000"
    if result["port"] != "7000":
        ok(f"Port set to {result['port']}.")
    else:
        info("Port: 7000 (default)")
    print()

    # Browser mode
    print(f"  {_c(C_CYAN, 'Browser automation (Playwright)')}")
    print(f"  {_c(C_DIM, 'Headless = background, Visible = shows browser window')}")
    print()
    result["browser_headless"] = (_select([
        "Headless  — runs in background, no window  (recommended)",
        "Visible   — shows browser window (useful for debugging)",
    ], default=0) == 0)
    ok(f"Browser: {'headless' if result['browser_headless'] else 'visible'}.")
    print()

    # ── Claude CLI (Subscription) ────────────────────────────────────────────
    print(f"  {_c(C_CYAN, 'Claude Subscription (Claude Code CLI)')}")
    print(f"  {_c(C_DIM, 'Use your Claude.ai subscription ($20/$200 plan) for coding tasks —')}")
    print(f"  {_c(C_DIM, 'no API key needed. AION delegates complex code to Claude automatically.')}")
    print()

    import subprocess as _sp
    claude_bin = _find_claude_bin()

    if claude_bin:
        ok(f"Claude CLI found: {claude_bin}")
        logged_in = _claude_cli_logged_in(claude_bin)
        if logged_in:
            ok("Claude CLI is authenticated and ready.")
            result["claude_cli"] = True
        else:
            warn("Claude CLI found but not logged in.")
            print()
            login_ans = ask("Run 'claude login' now to connect your subscription? (y/n)", "y")
            if login_ans.lower() in ("y", "yes", "j", "ja", ""):
                print()
                info("Opening browser for Claude login...")
                try:
                    _sp.run([claude_bin, "login"], timeout=120)
                    if _claude_cli_logged_in(claude_bin):
                        ok("Claude CLI authenticated successfully.")
                        result["claude_cli"] = True
                    else:
                        warn("Login may not have completed — verify with: claude --print 'hi'")
                        result["claude_cli"] = False
                except Exception as e:
                    warn(f"Login failed: {e}")
                    result["claude_cli"] = False
            else:
                info("Skipped — run 'claude login' later to activate.")
                result["claude_cli"] = False
    else:
        print(f"  {_c(C_DIM, 'Claude CLI not installed.')}")
        print()
        install_ans = ask("Install Claude Code CLI now? (y/n)", "n")
        if install_ans.lower() in ("y", "yes", "j", "ja"):
            print()
            info("Installing Claude Code via npm...")
            import shutil as _shutil
            npm = _shutil.which("npm")
            if not npm:
                warn("npm not found. Install Node.js first: https://nodejs.org")
                info("Then run: npm install -g @anthropic-ai/claude-code && claude login")
                result["claude_cli"] = False
            else:
                try:
                    r = _sp.run(
                        [npm, "install", "-g", "@anthropic-ai/claude-code"],
                        capture_output=True, text=True, timeout=120,
                    )
                    if r.returncode == 0:
                        ok("Claude Code CLI installed.")
                        claude_bin = _find_claude_bin()
                        if claude_bin:
                            print()
                            login_ans2 = ask("Run 'claude login' now to connect your subscription? (y/n)", "y")
                            if login_ans2.lower() in ("y", "yes", "j", "ja", ""):
                                _sp.run([claude_bin, "login"], timeout=120)
                                if _claude_cli_logged_in(claude_bin):
                                    ok("Claude CLI authenticated.")
                                    result["claude_cli"] = True
                                else:
                                    warn("Run 'claude login' manually to finish setup.")
                                    result["claude_cli"] = False
                            else:
                                info("Run 'claude login' later.")
                                result["claude_cli"] = False
                    else:
                        warn(f"npm install failed: {r.stderr[:200]}")
                        info("Manual install: npm install -g @anthropic-ai/claude-code")
                        result["claude_cli"] = False
                except Exception as e:
                    warn(f"Install error: {e}")
                    result["claude_cli"] = False
        else:
            info("Skipped — install later: npm install -g @anthropic-ai/claude-code")
            result["claude_cli"] = False

    # Task routing config
    if result.get("claude_cli"):
        print()
        print(f"  {_c(C_DIM, 'Task routing — which model handles which task type:')}")
        print(f"    {_c(C_WHITE, 'coding')}   → claude-opus-4-6  (best for writing/refactoring code)")
        print(f"    {_c(C_WHITE, 'review')}   → claude-sonnet-4-6  (fast + good for code review)")
        print(f"    {_c(C_WHITE, 'default')}  → your primary model  (everything else)")
        print()
        use_defaults = ask("Use these routing defaults? (y/n)", "y")
        if use_defaults.lower() in ("y", "yes", "j", "ja", ""):
            result["task_routing"] = {
                "coding":  "claude-opus-4-6",
                "review":  "claude-sonnet-4-6",
                "default": "gemini-2.5-flash",
            }
            ok("Task routing configured.")
        else:
            coding_model  = ask("Model for coding tasks", "claude-opus-4-6")
            default_model = ask("Default model (for everything else)", "gemini-2.5-flash")
            result["task_routing"] = {
                "coding":  coding_model,
                "default": default_model,
            }
            ok("Task routing saved.")
    print()

    # Docker
    print(f"  {_c(C_CYAN, 'Docker')}")
    print(f"  {_c(C_DIM, 'AION includes a Dockerfile and docker-compose.yml for containerized deployment.')}")
    print(f"  {_c(C_DIM, 'To run via Docker:  docker-compose up')}")
    print()
    info("No Docker configuration needed here — uses the same .env and config.json.")
    print()

    # TTS Engine
    print()
    print(f"  {_c(C_CYAN, 'Voice output (TTS)')}")
    print(f"  {_c(C_DIM, 'AION can read responses aloud.')}")
    print()
    tts_idx = _select([
        "off       — no voice  (default, recommended for most setups)",
        "edge-tts  — Microsoft neural TTS via internet  (best quality)",
        "sapi5     — Windows built-in TTS  (offline, no install)",
        "pyttsx3   — cross-platform offline TTS",
    ], default=0)
    result["tts_engine"] = ["off", "edge", "sapi5", "pyttsx3"][tts_idx]
    if result["tts_engine"] != "off":
        ok(f"TTS: {result['tts_engine']}")
        voice_default = "de-DE-KatjaNeural" if result["tts_engine"] == "edge" else ""
        voice = ask(f"Voice name (Enter = default{', e.g. ' + voice_default if voice_default else ''})", "")
        if voice:
            result["tts_voice"] = voice
            ok(f"Voice: {voice}")
        else:
            if voice_default:
                result["tts_voice"] = voice_default
            info(f"Voice: default{' (' + voice_default + ')' if voice_default else ''}")
    else:
        info("TTS: disabled")
    print()

    # Thinking Level
    print(f"  {_c(C_CYAN, 'Thinking depth')}")
    print(f"  {_c(C_DIM, 'How much internal reasoning AION does before answering.')}")
    print()
    thinking_idx = _select([
        "standard  — balanced quality/speed  (recommended)",
        "deep      — thorough reasoning for complex tasks",
        "minimal   — light thinking  (faster)",
        "off       — no thinking  (fastest, cheapest)",
    ], default=0)
    result["thinking_level"] = ["standard", "deep", "minimal", "off"][thinking_idx]
    ok(f"Thinking level: {result['thinking_level']}")
    print()

    return result


# ── Step 9: System Check ──────────────────────────────────────────────────────

def step7_systemcheck(provider: str, api_key: str, model: str) -> bool:
    section("System check", "Step 9/9:")

    all_ok = True

    # 1. Filesystem
    info("Filesystem ...")
    try:
        test_file = BOT_DIR / "_onboarding_test.tmp"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        ok("Filesystem writable")
    except Exception as e:
        err(f"Filesystem error: {e}")
        all_ok = False

    # 2. Internet
    info("Internet connection ...")
    try:
        import urllib.request
        urllib.request.urlopen("https://www.google.com", timeout=5)
        ok("Internet connection available")
    except Exception as e:
        warn(f"No internet or Google unreachable: {e}")

    # 3. API test
    if provider != "ollama":
        info(f"API test ({PROVIDERS[provider]['label']}) ...")
        try:
            if provider == "gemini":
                try:
                    import google.genai as genai
                    client = genai.Client(api_key=api_key)
                    resp = client.models.generate_content(
                        model=model,
                        contents="Reply with exactly: OK"
                    )
                    reply = getattr(resp, "text", "") or ""
                    if not reply and hasattr(resp, "candidates"):
                        reply = resp.candidates[0].content.parts[0].text
                    ok(f"Gemini API responded: {reply.strip()[:40]}")
                except ImportError:
                    warn("google-genai not installed — API test skipped")
            else:
                try:
                    import openai
                    p = PROVIDERS[provider]
                    kwargs = {"api_key": api_key}
                    if provider != "openai":
                        kwargs["base_url"] = {
                            "deepseek":  "https://api.deepseek.com",
                            "anthropic": "https://api.anthropic.com/v1",
                            "grok":      "https://api.x.ai/v1",
                        }.get(provider, "")
                    client = openai.OpenAI(**kwargs)
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                        max_tokens=5
                    )
                    reply = resp.choices[0].message.content or ""
                    ok(f"{p['label']} API responded: {reply.strip()[:40]}")
                except ImportError:
                    warn("openai not installed — API test skipped")
        except Exception as e:
            err(f"API test failed: {e}")
            all_ok = False
    else:
        info("Ollama: checking local server ...")
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:11434", timeout=3)
            ok("Ollama server is running")
        except Exception:
            warn("Ollama server not running — start with: ollama serve")

    # 4. Plugins
    info("Plugins ...")
    plugins_dir = BOT_DIR / "plugins"
    if plugins_dir.exists():
        count = sum(1 for p in plugins_dir.iterdir() if p.is_dir())
        ok(f"Plugin directory found: {count} plugin(s)")
    else:
        warn("Plugin directory not found")

    # 5. Playwright / Browser
    info("Browser automation (Playwright) ...")
    try:
        from playwright.sync_api import sync_playwright
        # Chromium starten als Funktionstest
        try:
            _pw = sync_playwright().start()
            _b  = _pw.chromium.launch(headless=True)
            _b.close()
            _pw.stop()
            ok("Playwright + Chromium ready")
        except Exception:
            # Playwright installiert, aber Chromium fehlt
            print()
            warn("Playwright is installed but Chromium is missing.")
            answer = ask("Install Chromium now? (recommended)", default="y").lower()
            if answer in ("y", "yes", "j", "ja", ""):
                info("Running: playwright install chromium ...")
                import subprocess
                result = subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    ok("Chromium installed successfully")
                else:
                    warn(f"Chromium install failed: {result.stderr[:200]}")
                    warn("Run manually: playwright install chromium")
            else:
                info("Skipped — run later: playwright install chromium")
    except ImportError:
        print()
        warn("Playwright not installed (browser automation won't be available).")
        answer = ask("Install Playwright + Chromium now? (recommended)", default="y").lower()
        if answer in ("y", "yes", "j", "ja", ""):
            info("Running: pip install playwright && playwright install chromium ...")
            import subprocess
            r1 = subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright", "-q"],
                capture_output=True, text=True
            )
            if r1.returncode == 0:
                r2 = subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    capture_output=True, text=True
                )
                if r2.returncode == 0:
                    ok("Playwright + Chromium installed successfully")
                else:
                    warn("Chromium install failed — run manually: playwright install chromium")
            else:
                warn(f"pip install playwright failed: {r1.stderr[:200]}")
        else:
            info("Skipped — run later: pip install playwright && playwright install chromium")

    # 6. Claude CLI
    info("Claude Code CLI (subscription provider) ...")
    claude_bin = _find_claude_bin()
    if claude_bin:
        logged_in = _claude_cli_logged_in(claude_bin)
        if logged_in:
            ok("Claude CLI ready — ask_claude tool available")
        else:
            warn("Claude CLI found but not authenticated — run: claude login")
    else:
        info("Claude CLI not installed — ask_claude tool unavailable (optional)")

    return all_ok

# ── Write Output ──────────────────────────────────────────────────────────────

def write_env(primary_provider: str, primary_key: str, model: str,
              extra_keys: dict, channels: dict, advanced: dict) -> None:
    env_path = BOT_DIR / ".env"
    lines = ["# AION Configuration — generated by onboarding.py"]

    # Primary provider key
    if primary_provider != "ollama":
        env_key = PROVIDERS[primary_provider]["key_env"]
        lines.append(f"{env_key}={primary_key}")

    # Additional provider keys
    for env_var, api_key in extra_keys.items():
        lines.append(f"{env_var}={api_key}")

    lines.append(f"AION_MODEL={model}")
    lines.append(f"AION_PORT={advanced.get('port', '7000')}")

    # Telegram
    if channels.get("TELEGRAM_BOT_TOKEN"):
        lines.append(f"TELEGRAM_BOT_TOKEN={channels['TELEGRAM_BOT_TOKEN']}")
    if channels.get("TELEGRAM_CHAT_ID"):
        lines.append(f"TELEGRAM_CHAT_ID={channels['TELEGRAM_CHAT_ID']}")

    # Discord
    if channels.get("DISCORD_BOT_TOKEN"):
        lines.append(f"DISCORD_BOT_TOKEN={channels['DISCORD_BOT_TOKEN']}")

    # Slack
    if channels.get("SLACK_BOT_TOKEN"):
        lines.append(f"SLACK_BOT_TOKEN={channels['SLACK_BOT_TOKEN']}")
    if channels.get("SLACK_APP_TOKEN"):
        lines.append(f"SLACK_APP_TOKEN={channels['SLACK_APP_TOKEN']}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok(f".env written ({env_path})")


def write_config(model: str, permissions: dict | None = None, advanced: dict | None = None) -> None:
    config_path = BOT_DIR / "config.json"
    cfg = {}
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg["model"] = model
    if permissions:
        cfg["permissions"] = permissions
    if advanced:
        if "browser_headless" in advanced:
            cfg["browser_headless"] = advanced["browser_headless"]
        if "task_routing" in advanced:
            cfg["task_routing"] = advanced["task_routing"]
        if "tts_engine" in advanced:
            cfg["tts_engine"] = advanced["tts_engine"]
        if "tts_voice" in advanced:
            cfg["tts_voice"] = advanced["tts_voice"]
        if "thinking_level" in advanced:
            cfg["thinking_level"] = advanced["thinking_level"]
    config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    ok(f"config.json written ({config_path})")


def update_character_md(profile: dict) -> None:
    char_path = BOT_DIR / "character.md"
    content   = char_path.read_text(encoding="utf-8") if char_path.exists() else ""

    # Remove existing onboarding section
    content = re.sub(
        r"\n## User Profile \(Onboarding\).*",
        "", content, flags=re.DOTALL
    )
    content = re.sub(
        r"\n## Nutzer-Profil \(Onboarding\).*",
        "", content, flags=re.DOTALL
    )
    content = content.rstrip()

    name   = profile.get("name", "")
    anrede = profile.get("anrede", "informal")
    lang   = profile.get("lang", "English")
    uses   = ", ".join(profile.get("uses", ["General"]))
    style  = profile.get("style", "Normal")
    extra  = profile.get("extra", "")

    section_lines = [
        "", "",
        "## User Profile (Onboarding)",
        f"- Name: {name}" if name else "- Name: (not provided)",
        f"- Address style: {anrede}",
        f"- Primary language: {lang}",
        f"- Primary use: {uses}",
        f"- Response style: {style}",
    ]
    if extra:
        section_lines.append(f"- Note: {extra}")

    content += "\n".join(section_lines) + "\n"
    char_path.write_text(content, encoding="utf-8")
    ok(f"character.md updated ({char_path})")


def write_flag() -> None:
    flag_path = BOT_DIR / "aion_onboarding_complete.flag"
    flag_path.write_text("Onboarding complete.\n", encoding="utf-8")
    ok(f"Flag file created ({flag_path})")


def completion_banner(model: str, name: str, extra_count: int,
                      channels: dict | None = None, advanced: dict | None = None) -> None:
    print()
    greeting = f"Hello, {name}! AION is ready." if name else "AION is ready."
    print(_c(C_GREEN, "  ===================================================="))
    print(_c(C_GREEN, "  Setup complete!"))
    print(f"  {_c(C_DIM, 'Model:     ')}{_c(C_CYAN, model)}")
    if extra_count:
        print(f"  {_c(C_DIM, 'Providers: ')}{_c(C_CYAN, str(extra_count + 1))} configured")

    # Show active channels
    if channels:
        active = []
        if channels.get("TELEGRAM_BOT_TOKEN"):
            active.append("Telegram")
        if channels.get("DISCORD_BOT_TOKEN"):
            active.append("Discord")
        if channels.get("SLACK_BOT_TOKEN"):
            active.append("Slack")
        if active:
            print(f"  {_c(C_DIM, 'Channels:  ')}{_c(C_CYAN, ', '.join(active))}")

    # Show TTS
    if advanced and advanced.get("tts_engine", "off") != "off":
        voice = advanced.get("tts_voice", "default")
        print(f"  {_c(C_DIM, 'TTS:       ')}{_c(C_CYAN, advanced['tts_engine'])}  {_c(C_DIM, f'({voice})')}")
    # Show thinking level
    if advanced and advanced.get("thinking_level") and advanced["thinking_level"] != "standard":
        print(f"  {_c(C_DIM, 'Thinking:  ')}{_c(C_CYAN, advanced['thinking_level'])}")

    # Show Claude CLI status
    if advanced and advanced.get("claude_cli"):
        routing = advanced.get("task_routing", {})
        coding_model = routing.get("coding", "claude-opus-4-6")
        print(f"  {_c(C_DIM, 'Claude:    ')}{_c(C_CYAN, f'ask_claude active — coding → {coding_model}')}")

    # Show port
    if advanced:
        port = advanced.get("port", "7000")
        print(f"  {_c(C_DIM, 'Web UI:    ')}{_c(C_CYAN, f'http://localhost:{port}')}")

    print(f"  {_c(C_WHITE, greeting)}")
    print(_c(C_GREEN, "  ===================================================="))
    print()
    print(f"  {_c(C_DIM, 'Start:              aion')}")
    print(f"  {_c(C_DIM, 'Terminal mode:      aion --cli')}")
    print(f"  {_c(C_DIM, 'Docker:             docker-compose up')}")
    print(f"  {_c(C_DIM, 'Re-run setup:       aion --setup')}")
    print()

# ── Main ──────────────────────────────────────────────────────────────────────

def run_onboarding() -> None:
    try:
        banner()

        provider     = step1_provider()
        api_key      = step2_apikey(provider)
        model        = step3_model(provider)
        extra_keys   = step4_additional_providers(provider)
        channels     = step5_channels()
        profile      = step6_profile()
        permissions  = step7_permissions()
        advanced     = step8_advanced()
        _ok          = step7_systemcheck(provider, api_key, model)

        # Write output
        print()
        section("Save configuration", "Saving:")

        write_env(provider, api_key, model, extra_keys, channels, advanced)
        write_config(model, permissions, advanced)
        update_character_md(profile)
        write_flag()

        completion_banner(model, profile.get("name", ""), len(extra_keys), channels, advanced)

    except KeyboardInterrupt:
        print()
        warn("Onboarding cancelled (Ctrl+C).")
        _pause_exit(1)
    except Exception as e:
        import traceback
        print()
        err(f"Unexpected error: {e}")
        print()
        print(traceback.format_exc())
        _pause_exit(1)


def _pause_exit(code: int) -> None:
    """Pause before exit on Windows so the user can read the error."""
    if sys.platform == "win32":
        try:
            input("\nPress Enter to close...")
        except Exception:
            pass
    sys.exit(code)


if __name__ == "__main__":
    run_onboarding()
