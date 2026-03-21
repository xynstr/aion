#!/usr/bin/env python3
"""
AION Onboarding — First-run Setup Wizard.
Automatically called on first start.
"""
import os
import sys
import json
import re

# UTF-8 on Windows
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
    try:
        import getpass
        val = getpass.getpass(f"  {_c(C_CYAN, prompt)}: ")
        return val.strip()
    except Exception:
        return ask(prompt)

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
    section("Choose your primary AI provider", "Step 1/7:")
    print(f"  {_c(C_DIM, 'This will be the default model. You can add more providers in step 2.')}")
    print()

    provider_list = list(PROVIDERS.keys())
    for i, pid in enumerate(provider_list, 1):
        p = PROVIDERS[pid]
        num   = _c(C_WHITE, str(i))
        label = _c(C_CYAN, f"{p['label']:<26}")
        note  = _c(C_DIM, p["note"])
        key_note = _c(C_DIM, "(no key needed)") if not p["key_env"] else ""
        print(f"    {num}  {label}  {note}  {key_note}")

    print()

    while True:
        choice = ask(f"Choice (1-{len(provider_list)})", "1")
        if choice.isdigit() and 1 <= int(choice) <= len(provider_list):
            return provider_list[int(choice) - 1]
        warn(f"Please enter a number between 1 and {len(provider_list)}.")

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
    section(f"API key for {PROVIDERS[provider]['label']}", "Step 2/7:")
    return _ask_api_key(provider)

# ── Step 3: Model ─────────────────────────────────────────────────────────────

def step3_model(provider: str) -> str:
    section("Choose a model", "Step 3/7:")
    p = PROVIDERS[provider]
    model_list    = p["models"]
    default_model = p["default_model"]

    print(f"  {_c(C_DIM, 'Available models for')} {_c(C_CYAN, p['label'])}:")
    print()

    for i, (name, desc) in enumerate(model_list, 1):
        is_default = name == default_model
        marker = _c(C_GREEN, " *") if is_default else "  "
        num    = _c(C_WHITE, str(i))
        mname  = _c(C_CYAN, f"{name:<36}")
        mdesc  = _c(C_DIM, desc)
        print(f"    {marker} {num}  {mname}  {mdesc}")

    print()
    print(f"  {_c(C_DIM, '* = default  |  Enter number or model name directly')}")
    print()

    default_idx = next(
        (str(i) for i, (n, _) in enumerate(model_list, 1) if n == default_model), "1"
    )

    while True:
        choice = ask(f"Model (1-{len(model_list)})", default_idx)
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(model_list):
                return model_list[idx - 1][0]
            warn(f"Please enter a number between 1 and {len(model_list)}.")
            continue
        known = [n for n, _ in model_list]
        if choice in known:
            return choice
        if choice:
            warn(f"Unknown model '{choice}'. Use anyway?")
            if ask("Confirm? (y/n)", "y").lower() != "n":
                return choice

# ── Step 4: Additional Providers ─────────────────────────────────────────────

def step4_additional_providers(primary: str) -> dict:
    section("Additional providers (optional)", "Step 4/7:")
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

# ── Step 5: Telegram ──────────────────────────────────────────────────────────

def step5_telegram() -> dict:
    section("Telegram (optional)", "Step 5/7:")
    print(f"  {_c(C_DIM, 'AION can send and receive messages via Telegram.')}")
    print()

    use_tg = ask("Set up Telegram? (y/n)", "n")
    if use_tg.lower() != "y":
        info("Telegram skipped.")
        return {}

    print()
    print(f"  {_c(C_DIM, 'Create a bot: @BotFather on Telegram')}")
    print(f"  {_c(C_DIM, 'Chat ID: Message the bot, then open https://api.telegram.org/bot<TOKEN>/getUpdates')}")
    print()

    token   = ask("Bot token (e.g. 123456:ABC-...)")
    chat_id = ask("Chat ID (e.g. 123456789)")

    if not token or not chat_id:
        warn("Token or chat ID missing — Telegram not configured.")
        return {}

    ok("Telegram credentials saved.")
    return {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat_id}

# ── Step 6: Profile ───────────────────────────────────────────────────────────

def step6_profile() -> dict:
    section("Your profile", "Step 6/7:")
    print(f"  {_c(C_DIM, 'Helps AION adapt to you from day one.')}")
    print()

    name = ask("Your name", "")

    print()
    print(f"  {_c(C_DIM, 'Address:')}")
    print(f"    {_c(C_WHITE, '1')}  informal (you)")
    print(f"    {_c(C_WHITE, '2')}  formal (Sir/Ma'am)")
    anrede = "informal" if ask("Address (1/2)", "1") != "2" else "formal"

    print()
    print(f"  {_c(C_DIM, 'Primary language:')}")
    print(f"    {_c(C_WHITE, '1')}  German")
    print(f"    {_c(C_WHITE, '2')}  English")
    print(f"    {_c(C_WHITE, '3')}  mixed")
    lang_map = {"1": "German", "2": "English", "3": "mixed"}
    lang = lang_map.get(ask("Language (1/2/3)", "1"), "German")

    print()
    print(f"  {_c(C_DIM, 'Primary use (comma-separated, e.g. \"1,3\"):')}")
    print(f"    {_c(C_WHITE, '1')}  Coding")
    print(f"    {_c(C_WHITE, '2')}  Research")
    print(f"    {_c(C_WHITE, '3')}  Productivity")
    print(f"    {_c(C_WHITE, '4')}  Creative writing")
    print(f"    {_c(C_WHITE, '5')}  General")
    use_map = {"1": "Coding", "2": "Research", "3": "Productivity",
               "4": "Creative writing", "5": "General"}
    use_input = ask("Selection", "5")
    uses = [use_map[p.strip()] for p in use_input.split(",") if p.strip() in use_map] or ["General"]

    print()
    print(f"  {_c(C_DIM, 'Response style:')}")
    print(f"    {_c(C_WHITE, '1')}  Short & concise")
    print(f"    {_c(C_WHITE, '2')}  Normal")
    print(f"    {_c(C_WHITE, '3')}  Detailed")
    style_map = {"1": "Short & concise", "2": "Normal", "3": "Detailed"}
    style = style_map.get(ask("Style (1/2/3)", "2"), "Normal")

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
    section("Permissions — what AION may do autonomously", "Step 7/8:")
    print(f"  {_c(C_DIM, 'Controls what AION does without asking you first.')}")
    print()
    print(f"    {_c(C_WHITE, '1')}  {_c(C_CYAN, 'Conservative')}  {_c(C_DIM, '— asks before anything that touches the system')}")
    print(f"    {_c(C_WHITE, '2')}  {_c(C_CYAN, 'Balanced')}      {_c(C_DIM, '— search/read/write free, shell/install/code needs OK  (recommended)')}")
    print(f"    {_c(C_WHITE, '3')}  {_c(C_CYAN, 'Autonomous')}    {_c(C_DIM, '— AION decides everything on its own')}")
    print()

    choice = ask("Preset (1/2/3)", "2")
    preset_map = {"1": "conservative", "2": "balanced", "3": "autonomous"}
    preset_name = preset_map.get(choice, "balanced")
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


# ── Step 8: System Check ──────────────────────────────────────────────────────

def step7_systemcheck(provider: str, api_key: str, model: str) -> bool:
    section("System check", "Step 8/8:")

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

    return all_ok

# ── Write Output ──────────────────────────────────────────────────────────────

def write_env(primary_provider: str, primary_key: str, model: str,
              extra_keys: dict, telegram: dict) -> None:
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
    lines.append("AION_PORT=7000")

    if telegram.get("TELEGRAM_BOT_TOKEN"):
        lines.append(f"TELEGRAM_BOT_TOKEN={telegram['TELEGRAM_BOT_TOKEN']}")
    if telegram.get("TELEGRAM_CHAT_ID"):
        lines.append(f"TELEGRAM_CHAT_ID={telegram['TELEGRAM_CHAT_ID']}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok(f".env written ({env_path})")


def write_config(model: str, permissions: dict | None = None) -> None:
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


def completion_banner(model: str, name: str, extra_count: int) -> None:
    print()
    greeting = f"Hello, {name}! AION is ready." if name else "AION is ready."
    print(_c(C_GREEN, "  ===================================================="))
    print(_c(C_GREEN, "  Setup complete!"))
    print(f"  {_c(C_DIM, 'Model:     ')}{_c(C_CYAN, model)}")
    if extra_count:
        print(f"  {_c(C_DIM, 'Providers: ')}{_c(C_CYAN, str(extra_count + 1))} configured")
    print(f"  {_c(C_WHITE, greeting)}")
    print(_c(C_GREEN, "  ===================================================="))
    print()
    print(f"  {_c(C_DIM, 'To switch models later: tell AION or use the System tab in the Web UI.')}")
    print(f"  {_c(C_DIM, 'To add providers later: add API keys to .env and restart AION.')}")
    print()

# ── Main ──────────────────────────────────────────────────────────────────────

def run_onboarding() -> None:
    try:
        banner()

        provider     = step1_provider()
        api_key      = step2_apikey(provider)
        model        = step3_model(provider)
        extra_keys   = step4_additional_providers(provider)
        telegram     = step5_telegram()
        profile      = step6_profile()
        permissions  = step7_permissions()
        _ok          = step7_systemcheck(provider, api_key, model)

        # Write output
        print()
        section("Save configuration", "Saving:")

        write_env(provider, api_key, model, extra_keys, telegram)
        write_config(model, permissions)
        update_character_md(profile)
        write_flag()

        completion_banner(model, profile.get("name", ""), len(extra_keys))

    except KeyboardInterrupt:
        print()
        warn("Onboarding cancelled (Ctrl+C).")
        sys.exit(1)
    except Exception as e:
        print()
        err(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_onboarding()
