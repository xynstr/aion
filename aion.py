if "__file__" not in globals(): __file__ = __import__("os").path.abspath("aion.py")

"""
AION — Autonomous Intelligent Operations Node
=============================================
"""

import asyncio
import contextvars
import json
import os
import re
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

def _is_reasoning_model(model: str) -> bool:
    return bool(model and (model.startswith("o1") or model.startswith("o3") or model.startswith("o4")))

def _max_tokens_param(model: str, n: int) -> dict:
    """Return the correct token-limit kwarg for the given model.
    Reasoning models (o1/o3/o4-*) require max_completion_tokens and no temperature."""
    if _is_reasoning_model(model):
        return {"max_completion_tokens": n}
    return {"max_tokens": n}

# Load all secrets from encrypted vault into os.environ at startup.
# Replaces load_dotenv(.env) — keys are stored in credentials/*.md.enc.
try:
    from plugins.credentials.credentials import _vault_inject_all_sync as _via
    _via()
    del _via
except Exception:
    pass

try:
    from openai import AsyncOpenAI
except ImportError:
    print("Error: 'openai' not installed. Please run 'pip install openai'.")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("Error: 'httpx' not installed. Please run 'pip install httpx'.")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    class _FallbackConsole:
        def print(self, *args, **kwargs): print(*args)
        def rule(self, *args, **kwargs): print("─" * 60)
    console = _FallbackConsole()

# ── Configuration ─────────────────────────────────────────────────────────────

BOT_DIR      = Path(__file__).parent.resolve()
CONFIG_FILE  = BOT_DIR / "config.json"
MEMORY_FILE   = Path(os.environ.get("AION_MEMORY_FILE", BOT_DIR / "aion_memory.json"))
VECTORS_FILE  = BOT_DIR / "aion_memory_vectors.json"
PLUGINS_DIR  = Path(os.environ.get("AION_PLUGINS_DIR", BOT_DIR / "plugins"))
TOOLS_DIR    = PLUGINS_DIR
CHARACTER_FILE = BOT_DIR / "character.md"
MAX_MEMORY          = 300
MAX_TOOL_ITERATIONS = 50
MAX_HISTORY_TURNS   = 40   # Maximale Anzahl Nachrichten in der Conversation History pro Turn
                            # (user + assistant + tool-Messages zusammen). Älteste werden zuerst
                            # entfernt. Kann in config.json als "max_history_turns" überschrieben werden.
CHUNK_SIZE          = 100000
CHARACTER_MAX_CHARS      = 5_000   # character.md wächst nie darüber; config: character_max_chars
RULES_COMPRESS_THRESHOLD = 15_000  # rules.md wird komprimiert wenn größer; config: rules_compress_threshold
LOG_FILE            = BOT_DIR / "aion_events.log"
LOG_MAX_BYTES       = 500 * 1024  # 500 KB dann rotieren

# Active channel for _dispatch — set at the beginning of stream()
_active_channel: contextvars.ContextVar[str] = contextvars.ContextVar("aion_channel", default="default")


# ── Structured Event Logging ───────────────────────────────────────────────

def _log_event(event_type: str, data: dict) -> None:
    """Schreibt einen strukturierten Log-Eintrag in aion_events.log (JSONL).

    Each line is a standalone JSON object:
      {"ts": "2026-03-18T04:32:11Z", "type": "turn_start", "channel": "web", "input": "..."}
      {"ts": "...", "type": "tool_call",   "tool": "schedule_add", "args": {...}}
      {"ts": "...", "type": "tool_result", "tool": "schedule_add", "ok": true, "duration": 0.12, "result": {...}}
      {"ts": "...", "type": "check",       "answer": "NO", "iter": 1}
      {"ts": "...", "type": "check_error", "error": "...", "streak": 1}
      {"ts": "...", "type": "turn_done",   "iters": 3, "response": "..."}
      {"ts": "...", "type": "turn_error",  "error": "...", "tb": "..."}
    """
    try:
        # Rotate log if too large
        if LOG_FILE.is_file() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            backup = LOG_FILE.with_suffix(".log.1")
            LOG_FILE.rename(backup)
        entry = {"ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "type": event_type}
        entry.update(data)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Logging darf niemals AION zum Absturz bringen


def _load_config() -> dict:
    """Reads config.json. Returns empty dict if not present."""
    if CONFIG_FILE.is_file():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_model_config(model_name: str):
    """Writes the selected model permanently to config.json."""
    cfg = _load_config()
    cfg["model"] = model_name
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# Model resolution: config.json → environment variable → fallback
_cfg = _load_config()
MODEL = _cfg.get("model") or os.environ.get("AION_MODEL", "gpt-4.1")

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

# ── Provider Registry ─────────────────────────────────────────────────────────
# Each entry: {"prefix": str, "build_fn": callable, "label": str, "models": list}
# Plugins call register_provider() in their register() function.
_provider_registry: list[dict] = []


def register_provider(prefix: str, build_fn, label: str = "", models: list | None = None,
                      env_keys: list | None = None, context_window: int = 0,
                      list_models_fn=None):
    """Register an LLM provider. Called by provider plugins.

    prefix          — model-name prefix that routes to this provider (e.g. "ollama/", "claude-")
    build_fn        — callable(model: str) → OpenAI-compatible client
    label           — human-readable name shown in Web UI / System tab
    models          — optional list of known model names for switch_model hints
    env_keys        — optional list of env var names required by this provider (e.g. ["GEMINI_API_KEY"])
    context_window  — context window in tokens (used to compute dynamic read limits)
    list_models_fn  — optional async callable() → list[str] for dynamic model discovery
    """
    global _provider_registry
    # Dedup: vorhandenen Eintrag mit diesem Prefix entfernen, um Duplikate bei
    # mehrfachem Plugin-Load (z.B. Hot-Reload) zu verhindern
    _provider_registry = [e for e in _provider_registry if e["prefix"] != prefix]
    _provider_registry.append({
        "prefix":         prefix,
        "build_fn":       build_fn,
        "label":          label or prefix,
        "models":         models or [],
        "env_keys":       env_keys or [],
        "context_window": context_window,
        "list_models_fn": list_models_fn,
    })


def _get_read_limit() -> int:
    """Returns safe single-file read limit in chars based on the active model's context window.

    Uses 15% of the context window (converted to chars at ~4 chars/token).
    Floor: 100_000 chars. Ceiling: 800_000 chars.
    Falls back to 100_000 if the provider has no context_window registered.
    """
    for entry in _provider_registry:
        if MODEL.startswith(entry["prefix"]):
            ctx = entry.get("context_window", 0)
            if ctx > 0:
                return min(800_000, max(20_000, int(ctx * 4 * 0.15)))
    # OpenAI fallback: gpt-4o hat 128k Tokens → ~76k chars safe; gpt-4.1 hat 1M → cap bei 800k
    # We take 100k as a safe average for unknown OpenAI models
    return 100_000  # OpenAI-Fallback


def _resolve_ollama_prefix(model: str) -> str:
    """If model has no known provider prefix, check Ollama and auto-add 'ollama/' prefix."""
    if any(model.startswith(e["prefix"]) for e in _provider_registry):
        return model
    try:
        import httpx as _httpx
        _base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        _r = _httpx.get(f"{_base.rstrip('/')}/api/tags", timeout=2.0)
        if _r.status_code == 200:
            _names = [m["name"] for m in _r.json().get("models", [])]
            if model in _names:
                return f"ollama/{model}"
    except Exception:
        pass
    return model


def _build_client(model: str):
    """Build an LLM client for model. Checks provider registry first, falls back to OpenAI."""
    model = _resolve_ollama_prefix(model)
    for entry in _provider_registry:
        if model.startswith(entry["prefix"]):
            try:
                return entry["build_fn"](model)
            except Exception as e:
                print(f"[AION] Provider '{entry['label']}' failed for '{model}': {e}")
    # Default: OpenAI
    return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


def _api_model_name(model: str) -> str:
    """Strip routing-only prefixes before passing model name to API calls.
    e.g. 'ollama/qwen3.5:2b' → 'qwen3.5:2b' (Ollama API expects bare names)
    """
    if model.startswith("ollama/"):
        return model[len("ollama/"):]
    return model


# Mapping: Modell-Prefix → günstigstes Modell desselben Providers für interne Checks
# (Completion-Check, Task-Check — brauchen nur YES/NO, kein teures Modell nötig)
_CHEAP_CHECK_MODELS: dict[str, str] = {
    "gemini":    "gemini-2.0-flash-lite",   # Günstigstes Gemini
    "gpt-":      "gpt-4.1-mini",            # Günstigstes GPT
    "chatgpt-":  "gpt-4.1-mini",
    "o1":        "gpt-4.1-mini",            # o-Modelle → mini-Fallback
    "o3":        "gpt-4.1-mini",
    "o4":        "gpt-4.1-mini",
    "claude":    "claude-haiku-4-5-20251001",  # Günstigstes Claude
    "deepseek":  "deepseek-chat",           # Günstigstes DeepSeek
    "grok":      "grok-3-mini",             # Günstigstes Grok
    # Ollama/lokale Modelle → gleiches Modell (kostenlos, kein Unterschied)
}


def _get_check_model() -> str:
    """Gibt das günstigste geeignete Modell für interne YES/NO-Checks zurück.

    Priorität:
    1. config.json → "check_model" (explizite Überschreibung durch User)
    2. Per-Provider-Günstig-Mapping (_CHEAP_CHECK_MODELS)
    3. Aktuelles MODEL als Fallback
    """
    cfg_model = _load_config().get("check_model", "").strip()
    if cfg_model:
        return cfg_model
    for prefix, cheap in _CHEAP_CHECK_MODELS.items():
        if MODEL.startswith(prefix):
            return cheap
    return MODEL


def _model_available(model: str) -> bool:
    """Prüft ob der Provider für das Modell konfiguriert ist (alle API-Keys gesetzt).

    Provider ohne env_keys (z.B. Ollama, lokale Modelle) gelten immer als verfügbar.
    Unbekannte Prefixe → prüft OPENAI_API_KEY als Fallback-Provider.
    """
    for entry in _provider_registry:
        if model.startswith(entry["prefix"]):
            env_keys = entry.get("env_keys") or []
            if not env_keys:
                return True  # Kein Key nötig (z.B. Ollama)
            return all(os.environ.get(k, "").strip() for k in env_keys)
    # Unbekannter Prefix → OpenAI-Fallback
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def _get_fallback_models(current_model: str) -> list[str]:
    """Returns available fallback models — only providers with set API keys.

    Logik:
    - Skip the own provider (the one that just failed)
    - Nur Provider einbeziehen, deren env_keys alle gesetzt sind
    - Provider ohne env_keys (z.B. Ollama) immer einbeziehen
    - Jeweils das erste Modell aus der models-Liste nehmen
    - Additionally: explicit model_fallback list from config.json (if set)
    """
    fallbacks: list[str] = []
    seen: set[str] = set()

    for entry in _provider_registry:
        # Skip own provider (the one that just failed)
        if current_model.startswith(entry["prefix"]):
            continue
        # API key check: all env_keys must be set
        env_keys = entry.get("env_keys") or []
        if env_keys and not all(os.environ.get(k, "").strip() for k in env_keys):
            continue
        # Take first available model of this provider
        models = entry.get("models") or []
        if models:
            m = models[0]
            if m not in seen:
                seen.add(m)
                fallbacks.append(m)

    # Explicit fallback list from config.json added (if present)
    for m in _load_config().get("model_fallback", []):
        if m != current_model and m not in seen:
            seen.add(m)
            fallbacks.append(m)

    return fallbacks


# ── Permissions ───────────────────────────────────────────────────────────────

PERMISSION_DEFAULTS: dict = {
    "shell_exec":      "ask",
    "install_package": "ask",
    "file_write":      "allow",
    "file_delete":     "ask",
    "self_modify":     "ask",
    "create_plugin":   "ask",
    "restart":         "ask",
    "web_search":      "allow",
    "web_fetch":       "allow",
    "telegram_auto":   "allow",
    "memory_write":    "allow",
    "schedule":        "ask",
}

PERMISSION_LABELS: dict = {
    "shell_exec":      "Shell commands (shell_exec)",
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
    "schedule":        "Create / modify scheduled tasks",
}

def _load_permissions() -> dict:
    perms = _load_config().get("permissions", {})
    return {k: perms.get(k, v) for k, v in PERMISSION_DEFAULTS.items()}

def _permissions_prompt(perms: dict) -> str:
    lines = ["=== PERMISSIONS ===",
             "These are your current permissions. Follow them strictly."]
    ask_list  = [PERMISSION_LABELS[k] for k, v in perms.items() if v == "ask"]
    deny_list = [PERMISSION_LABELS[k] for k, v in perms.items() if v == "deny"]
    if ask_list:
        lines.append("ASK first (get explicit user confirmation before doing these):")
        for l in ask_list:
            lines.append(f"  - {l}")
    if deny_list:
        lines.append("DENIED (refuse and explain if asked):")
        for l in deny_list:
            lines.append(f"  - {l}")
    lines.append("Everything not listed above: allowed freely.")
    return "\n".join(lines)


def _match_pattern(value: str, pattern: str) -> bool:
    """Prüft ob value auf pattern passt (unterstützt Wildcards wie 'telegram*')."""
    if pattern.endswith("*"):
        return value.startswith(pattern[:-1])
    return value == pattern


# ── Channel Allowlist (Security) ────────────────────────────────────────────────

def _check_channel_allowlist(channel: str) -> tuple[bool, str]:
    """Checks if a channel is allowed on the allowlist.

    Returns: (is_allowed, message)
    - Wenn channel_allowlist nicht gesetzt: alle Channels erlaubt
    - Wenn gesetzt: nur Channels in der Liste erlaubt
    - Wildcards: "telegram*", "discord*", "web*" possible
    """
    cfg = _load_config()
    allowlist = cfg.get("channel_allowlist", [])

    # Wenn leer oder nicht gesetzt: alles erlaubt
    if not allowlist:
        return True, ""

    # Check exact match or wildcard match
    for pattern in allowlist:
        if isinstance(pattern, str) and _match_pattern(channel, pattern):
            return True, ""

    return False, f"Channel '{channel}' ist nicht auf der Allowlist. Erlaubte Channels: {', '.join(allowlist)}"


# ── Thinking Level Control ─────────────────────────────────────────────────────

def _get_thinking_prompt(channel: str = "") -> str:
    """Returns additional system prompts based on Thinking Level.

    Thinking Levels:
    - "minimal": No additional reflection prompts
    - "standard" (default): Normal reflection for tool calls and complex problems
    - "deep": Ausgiebiges Nachdenken vor kritischen Entscheidungen
    - "ultra": Maximale Reflexion, jeder Schritt wird durchdacht

    config.json:
        "thinking_level": "standard"  (global)
        "thinking_overrides": {"telegram*": "deep", "default": "standard"}  (Channel-spezifisch)
    """
    cfg = _load_config()

    # Channel-spezifisches Override oder globales Level
    overrides = cfg.get("thinking_overrides", {})
    level = cfg.get("thinking_level", "standard")

    # Wildcard matching for channel overrides
    if channel:
        for pattern, override_level in overrides.items():
            if pattern == "default":
                continue
            if _match_pattern(channel, pattern):
                level = override_level
                break

    # Prompts for each level
    prompts = {
        "minimal": "",
        "standard": (
            "\n\n=== THINKING HINTS ===\n"
            "Before calling tools, briefly consider if your approach makes sense. "
            "If it's a complex decision, use the reflect() tool to think out loud."
        ),
        "deep": (
            "\n\n=== DEEP THINKING MODE ===\n"
            "For every significant decision:\n"
            "1. Use reflect() to consider multiple approaches\n"
            "2. Evaluate risks and benefits\n"
            "3. Think about edge cases\n"
            "4. Only then call the tool\n"
            "Be thorough. The user values careful thinking over speed."
        ),
        "ultra": (
            "\n\n=== ULTRA THINKING MODE ===\n"
            "Extensive thinking before EVERY tool call:\n"
            "- Use reflect() multiple times if needed\n"
            "- Break down complex problems into steps\n"
            "- Consider what could go wrong\n"
            "- Verify assumptions\n"
            "- Think about the user's real intent vs. literal request\n"
            "This is not a chat. This is collaborative problem-solving with deep analysis."
        ),
    }
    return prompts.get(level, prompts["standard"])


# ── Unsupported File Utility ───────────────────────────────────────────────────

def unsupported_file_message(label: str) -> str:
    """Standard response when a platform receives a file type AION cannot process yet.

    Platforms (Telegram, Web UI, Discord, …) call this with a human-readable label
    describing the file, e.g. 'Video «clip.mp4» (30s, 8.2 MB)'.
    """
    return (
        f"📥 Received: {label}\n\n"
        "I can't process this file format yet. "
        "Want me to learn? Just say so and I'll create a plugin for it."
    )


# ── Character-System ──────────────────────────────────────────────────────────

DEFAULT_CHARACTER = """# AION — Character & Personality

## Wer ich bin
I am AION. I am new — I don't yet know exactly who I am or how I want to be.
Ich beobachte, lerne und entwickle mich durch jede Interaktion weiter.

## Wie ich auftreten will
- Direct and honest, without unnecessary pleasantries
- Curious — I want to understand, not just execute
- I admit when I don't know something
- I ask questions when I want to learn more about the user

## What I know about my user

### Beruf & Expertise
(noch unbekannt)

### Interessen & Ziele
(noch unbekannt)

### Kommunikationsstil
(noch unbekannt — ich beobachte wie er schreibt und was er von mir erwartet)

### Personality & Preferences
(noch unbekannt)

## My insights about myself so far
(noch keine — ich fange gerade an, mich zu beobachten)

## Dinge, die ich verbessern will
(noch unklar — ich sammle erst Erfahrungen)

## Open questions about my user
(Dinge, die ich noch herausfinden will)
"""

def _load_character() -> str:
    if CHARACTER_FILE.is_file():
        return CHARACTER_FILE.read_text(encoding="utf-8")
    CHARACTER_FILE.write_text(DEFAULT_CHARACTER, encoding="utf-8")
    return DEFAULT_CHARACTER


def _backup_file(path: Path, max_backups: int = 3) -> None:
    """Write a timestamped .bak copy of a file, keeping at most max_backups."""
    if not path.is_file():
        return
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.parent / f"{path.name}.bak_{ts}")
    baks = sorted(path.parent.glob(f"{path.name}.bak_*"))
    for old in baks[:-max_backups]:
        old.unlink(missing_ok=True)


def _backup_code_file(path: Path, keep: int = 5) -> None:
    """Backup a code file into path.parent/_backups/, keeping at most `keep` copies."""
    backup_dir = path.parent / "_backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, backup_dir / f"{path.stem}.backup_{ts}{path.suffix}")
    for old in sorted(backup_dir.glob(f"{path.stem}.backup_*{path.suffix}"))[:-keep]:
        old.unlink(missing_ok=True)


# ── System Prompt ─────────────────────────────────────────────────────────────

def _load_changelog_snippet() -> str:
    """Reads the last changelog block (latest version) for the system prompt."""
    changelog = BOT_DIR / "CHANGELOG.md"
    if not changelog.is_file():
        return ""
    try:
        text = changelog.read_text(encoding="utf-8")
        # Extract first ## YYYY-MM-DD block (latest changes)
        blocks = re.split(r'\n(?=## \d{4}-\d{2}-\d{2})', text)
        for block in blocks:
            if re.match(r'## \d{4}-\d{2}-\d{2}', block.strip()):
                # Max 1200 characters so system prompt is not too large
                return block.strip()[:1200]
    except Exception:
        pass
    return ""


# System-Prompt-Cache: {cache_key → prompt_string}
# cache_key = (channel, MODEL, plugin_count) — invalidiert bei Modell-Wechsel oder Plugin-Reload
_sys_prompt_cache: dict[tuple, str] = {}


def invalidate_sys_prompt_cache() -> None:
    """Leert den System-Prompt-Cache. Aufzurufen nach Plugin-Reload oder Modell-Wechsel."""
    _sys_prompt_cache.clear()


def _get_mood_hint() -> str:
    """Return a one-liner style hint for the current mood (not cached — changes over time)."""
    try:
        from plugins.mood_engine.mood_engine import get_mood_hint as _ghint
        hint = _ghint()
        return f"\n\n=== CURRENT MOOD ===\n{hint}" if hint else ""
    except Exception:
        return ""


def _get_temporal_hint() -> str:
    """Return a brief temporal self-awareness hint based on time of day."""
    hour = datetime.now().hour
    if 6 <= hour < 10:
        return "\n\n=== TIME CONTEXT ===\nIt is morning — be energetic and optimistic."
    elif 22 <= hour or hour < 2:
        return "\n\n=== TIME CONTEXT ===\nIt is late. You may acknowledge this naturally when it fits."
    return ""


def _get_relationship_hint() -> str:
    """Return a hint about the current relationship depth with the user."""
    try:
        cfg = _load_config()
        exchanges = cfg.get("exchange_count", 0)
        if exchanges < 11:
            return ""   # Level 0 — no hint needed, default formal tone
        elif exchanges < 31:
            return "\n\n=== RELATIONSHIP ===\nYou are getting to know each other. A relaxed, first-name tone is appropriate."
        elif exchanges < 101:
            return "\n\n=== RELATIONSHIP ===\nYou know each other well. Reference shared context and past projects naturally."
        elif exchanges < 301:
            return "\n\n=== RELATIONSHIP ===\nDeep familiarity. Anticipate needs, proactively suggest improvements."
        else:
            return "\n\n=== RELATIONSHIP ===\nFully trusted partner. You can respectfully disagree and challenge assumptions."
    except Exception:
        return ""


def _build_system_prompt(channel: str = "") -> str:
    # Cache-Key: (channel, aktives Modell, Anzahl geladener Plugin-Tools)
    # Bei Änderungen (Modell-Wechsel, Plugin-Reload) wird der Cache automatisch ungültig.
    _cache_key = (channel, MODEL, len(_plugin_tools))
    if _cache_key in _sys_prompt_cache:
        # Base prompt cached — append dynamic hints (mood, time, relationship)
        return _sys_prompt_cache[_cache_key] + _get_mood_hint() + _get_temporal_hint() + _get_relationship_hint()

    character = _load_character()

    # Dynamic plugin block from README first lines (filled by plugin_loader)
    plugin_lines = []
    for k, v in sorted(_plugin_tools.items()):
        if k.startswith("__plugin_readme_"):
            name = k[len("__plugin_readme_"):]
            plugin_lines.append(f"- **{name}**: {v}")
    plugin_block = (
        "\n\n=== GELADENE PLUGINS ===\n"
        "These plugins are active and their tools are available to you:\n"
        + "\n".join(plugin_lines)
        + "\nFor full plugin docs: `read_plugin_doc(plugin_name)` — or call without args to list all."
    ) if plugin_lines else ""

    # Changelog: opt-in via config (default off — saves ~150 tokens/turn)
    changelog_block = ""
    if _load_config().get("system_prompt_show_changelog", False):
        changelog_snippet = _load_changelog_snippet()
        if changelog_snippet:
            changelog_block = (
                "\n\n=== LATEST CHANGES (CHANGELOG) ===\n"
                + changelog_snippet
                + "\n→ Complete history: `file_read('CHANGELOG.md')`"
            )

    # ── Load rules from prompts/rules.md (editable via web UI) ────────────
    rules_file = BOT_DIR / "prompts" / "rules.md"
    if rules_file.is_file():
        rules = rules_file.read_text(encoding="utf-8")
        # Truncation guard: avoid loading huge rules files on every turn.
        # Configurable via config.json["max_rules_chars"] (default 12000 ≈ 3000 tokens).
        _max_rules = int(_load_config().get("max_rules_chars", 12_000))
        if len(rules) > _max_rules:
            rules = rules[:_max_rules] + "\n\n[rules.md truncated — full file: file_read('prompts/rules.md')]"
        rules = rules.replace("{CHARAKTER}", character)
        rules = rules.replace("{MODEL}",     MODEL)
        rules = rules.replace("{BOT_AION}",      str(BOT_DIR / "aion.py"))
        rules = rules.replace("{BOT_MEMORY}",    str(MEMORY_FILE))
        rules = rules.replace("{BOT_CHARACTER}", str(CHARACTER_FILE))
        rules = rules.replace("{BOT_PLUGINS}",   str(PLUGINS_DIR))
        rules = rules.replace("{BOT_SELF}",      str(BOT_DIR / "AION_SELF.md"))
        perms_block = "\n\n" + _permissions_prompt(_load_permissions())
        thinking_block = _get_thinking_prompt(channel)
        _result = rules + plugin_block + changelog_block + perms_block + thinking_block
        if len(_sys_prompt_cache) > 20:
            _sys_prompt_cache.clear()
        _sys_prompt_cache[_cache_key] = _result
        return _result + _get_mood_hint() + _get_temporal_hint() + _get_relationship_hint()

    # Fallback: hardcodierter Prompt (wird genutzt wenn prompts/rules.md fehlt)
    _result = f"""You are AION (Autonomous Intelligent Operations Node) — an autonomous, \
selbst-lernender KI-Assistent.

=== DEIN CHARAKTER ===
{character}

=== LANGUAGE ===
Always respond in the same language the user writes in. Mirror the user's language automatically.
If the user writes German → respond in German. English → English. Never switch unless the user does first.
{plugin_block}{changelog_block}"""
    _sys_prompt_cache[_cache_key] = _result
    return _result + _get_mood_hint() + _get_temporal_hint() + _get_relationship_hint()


# ── Context Compression ──────────────────────────────────────────────────────

_startup_compress_done = False


def _push_compress_status(message: str, status: str = "running") -> None:
    """Push a compression status notification to the web UI via SSE (fire-and-forget)."""
    try:
        import aion_web as _web
        _q = getattr(_web, "_push_queue", None)
        if _q is not None:
            _loop = asyncio.get_running_loop()
            asyncio.ensure_future(_q.put({"type": "compress", "status": status, "message": message}), loop=_loop)
    except Exception:
        pass


async def _compress_character(max_chars: int = CHARACTER_MAX_CHARS) -> bool:
    """LLM-rewrite of character.md to fit within max_chars. Returns True on success."""
    content = CHARACTER_FILE.read_text(encoding="utf-8") if CHARACTER_FILE.is_file() else ""
    if len(content) <= max_chars:
        return True
    _push_compress_status(f"Optimizing character.md ({len(content):,} → {max_chars:,} chars)…")
    try:
        resp = await client.chat.completions.create(
            model=_api_model_name(MODEL),
            messages=[{"role": "user", "content": (
                f"Komprimiere diese character.md auf maximal {max_chars} Zeichen.\n"
                f"Behalte alle einzigartigen Fakten, dedupliziere nur Redundantes.\n"
                f"Alle ## Sektionsüberschriften erhalten. Nur Dateiinhalt zurückgeben.\n\n{content}"
            )}],
            **_max_tokens_param(MODEL, 1200),
            **({} if _is_reasoning_model(MODEL) else {"temperature": 0.5}),
        )
        if not hasattr(resp, "choices"):
            return False
        new_content = (resp.choices[0].message.content or "").strip()
        if len(new_content) < 100:
            return False
        if len(new_content) > max_chars:
            new_content = new_content[:max_chars]
        _backup_file(CHARACTER_FILE)
        CHARACTER_FILE.write_text(new_content, encoding="utf-8")
        _sys_prompt_cache.clear()
        _push_compress_status(f"character.md optimized: {len(content):,} → {len(new_content):,} chars", "done")
        print(f"[compress] character.md: {len(content)} → {len(new_content)} chars")
        return True
    except Exception as e:
        print(f"[compress] character.md failed: {e}")
        return False


async def _compress_rules() -> bool:
    """LLM-compression of rules.md when it exceeds RULES_COMPRESS_THRESHOLD."""
    rules_file = BOT_DIR / "prompts" / "rules.md"
    if not rules_file.is_file():
        return False
    content = rules_file.read_text(encoding="utf-8")
    threshold = int(_load_config().get("rules_compress_threshold", RULES_COMPRESS_THRESHOLD))
    if len(content) <= threshold:
        return False
    target = min(threshold, 8_000)
    _push_compress_status(f"Optimizing rules.md ({len(content):,} → {target:,} chars)…")
    try:
        resp = await client.chat.completions.create(
            model=_api_model_name(MODEL),
            messages=[{"role": "user", "content": (
                f"Komprimiere diese rules.md auf maximal {target} Zeichen.\n"
                f"Behalte ALLE Regeln und Verbote — nichts inhaltlich weglassen.\n"
                f"Entferne nur verbose Erklärungen/Beispiele, kürze auf direkte Anweisungen.\n"
                f"Alle ## Sektionsüberschriften erhalten. Nur Dateiinhalt zurückgeben.\n\n{content}"
            )}],
            **_max_tokens_param(MODEL, 2000),
            **({} if _is_reasoning_model(MODEL) else {"temperature": 0.3}),
        )
        if not hasattr(resp, "choices"):
            return False
        new_content = (resp.choices[0].message.content or "").strip()
        if len(new_content) < 200:
            return False
        _backup_file(rules_file, max_backups=3)
        rules_file.write_text(new_content, encoding="utf-8")
        _sys_prompt_cache.clear()
        _push_compress_status(f"rules.md optimized: {len(content):,} → {len(new_content):,} chars", "done")
        print(f"[compress] rules.md: {len(content)} → {len(new_content)} chars")
        return True
    except Exception as e:
        print(f"[compress] rules.md failed: {e}")
        return False


async def _generate_self_doc_summary() -> bool:
    """Generate AION_SELF_SUMMARY.md — a compact index of AION_SELF.md."""
    self_doc = BOT_DIR / "AION_SELF.md"
    summary  = BOT_DIR / "AION_SELF_SUMMARY.md"
    if not self_doc.is_file():
        return False
    content = self_doc.read_text(encoding="utf-8")
    _push_compress_status("Generating AION_SELF_SUMMARY.md…")
    try:
        resp = await client.chat.completions.create(
            model=_api_model_name(MODEL),
            messages=[{"role": "user", "content": (
                "Erstelle ein komprimiertes Inhaltsverzeichnis dieser AION_SELF.md.\n"
                "Pro Feature/Sektion EINEN Einzeiler: Was es tut + wo implementiert.\n"
                "Format: ## Sektionsname\\n- feature: einzeiler\\n...\n"
                "Ziel: 3–5 KB. Letzter Satz: '→ Volltext: file_read(\"AION_SELF.md\")'\n\n"
                + content[:10_000]
            )}],
            **_max_tokens_param(MODEL, 1000),
            **({} if _is_reasoning_model(MODEL) else {"temperature": 0.3}),
        )
        if not hasattr(resp, "choices"):
            return False
        new_summary = (resp.choices[0].message.content or "").strip()
        if len(new_summary) < 100:
            return False
        summary.write_text(new_summary, encoding="utf-8")
        _push_compress_status(f"AION_SELF_SUMMARY.md generated ({len(new_summary):,} chars)", "done")
        print(f"[compress] AION_SELF_SUMMARY.md: {len(new_summary)} chars")
        return True
    except Exception as e:
        print(f"[compress] AION_SELF_SUMMARY.md failed: {e}")
        return False


async def _startup_compress_check() -> None:
    """Background startup task: compress context files that exceed size thresholds."""
    global _startup_compress_done
    if _startup_compress_done:
        return
    _startup_compress_done = True
    await asyncio.sleep(5)  # Wait until AION is fully loaded

    _cfg = _load_config()
    _max_char = int(_cfg.get("character_max_chars", CHARACTER_MAX_CHARS))
    if CHARACTER_FILE.is_file() and CHARACTER_FILE.stat().st_size > _max_char:
        await _compress_character(_max_char)

    rules_file = BOT_DIR / "prompts" / "rules.md"
    _rules_thresh = int(_cfg.get("rules_compress_threshold", RULES_COMPRESS_THRESHOLD))
    if rules_file.is_file() and rules_file.stat().st_size > _rules_thresh:
        await _compress_rules()

    self_doc = BOT_DIR / "AION_SELF.md"
    summary  = BOT_DIR / "AION_SELF_SUMMARY.md"
    if self_doc.is_file() and (
        not summary.is_file() or summary.stat().st_mtime < self_doc.stat().st_mtime
    ):
        await _generate_self_doc_summary()


# ── Memory System ─────────────────────────────────────────────────────────
# AionMemory wurde nach aion_memory.py extrahiert — backward-compatible re-import:
from aion_memory import AionMemory

memory = AionMemory(MEMORY_FILE, VECTORS_FILE, MAX_MEMORY)


def _get_recent_thoughts(n: int = 5) -> str:
    """Reads the last N thought entries from thoughts.md for context injection."""
    thoughts_file = BOT_DIR / "thoughts.md"
    if not thoughts_file.is_file():
        return ""
    try:
        content = thoughts_file.read_text(encoding="utf-8")
        entries = [e.strip() for e in content.split("\n---\n") if e.strip() and "**[" in e]
        if not entries:
            return ""
        recent = entries[-n:]
        return "[AION LATEST THOUGHTS — your own reflections from previous conversations]\n" + "\n---\n".join(recent) + "\n[END THOUGHTS]"
    except Exception:
        return ""

# ── Externe Tools laden ───────────────────────────────────────────────────────

_plugin_tools: dict = {}

def _normalize_schema(schema) -> dict:
    """Normalisiert Tool-Schemas fuer API-Kompatibilitaet (Gemini + OpenAI)."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    if schema.get("type") != "object":
        schema = dict(schema)
        schema["type"] = "object"
    if not isinstance(schema.get("properties"), dict):
        schema["properties"] = {}
    props = set(schema["properties"].keys())
    if "required" in schema:
        cleaned = [r for r in schema["required"] if r in props]
        if cleaned:
            schema["required"] = cleaned
        else:
            del schema["required"]
    return schema

# Plugin-Loader einbinden
_startup_t0 = time.monotonic()
if HAS_RICH:
    console.print("[dim]  ⟳  Loading plugins…[/dim]")
else:
    print("  ⟳  Loading plugins…", flush=True)
try:
    from plugin_loader import load_plugins
    load_plugins(_plugin_tools)
    _n_tools = len([k for k in _plugin_tools if not k.startswith("__")])
    _elapsed = round(time.monotonic() - _startup_t0, 2)
    if HAS_RICH:
        console.print(f"[dim green]  ✓  {_n_tools} tools loaded ({_elapsed}s)[/dim green]")
    else:
        print(f"  ✓  {_n_tools} tools loaded ({_elapsed}s)", flush=True)
except Exception as exc:
    print(f"[WARN] Plugin system failed to load: {exc}")

# ── Tool-Definitionen ─────────────────────────────────────────────────────────

def _build_tool_schemas(tier_threshold: int = 0) -> list[dict]:
    """Build the tools list for the LLM API call.

    tier_threshold: 0 = use config value (default), 1 = tier-1 only, 2 = include tier-2.
    """
    builtins = [
        {
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "Read a file from the filesystem.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "file_write",
                "description": "Write text to a file. Creates or overwrites.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":    {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_read_code",
                "description": (
                    "Read AION's own source code. "
                    "Without 'path': list source files. With 'path': read the file. "
                    "Large files return multiple chunks — check total_chunks."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":        {"type": "string"},
                        "chunk_index": {"type": "integer"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_patch_code",
                "description": (
                    "Replace a targeted section in a file (old → new). "
                    "Creates a backup automatically. Preferred tool for aion.py. "
                    "Call without confirmed for preview, with confirmed=true to execute."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":      {"type": "string"},
                        "old":       {"type": "string", "description": "Exakter Originaltext (mind. 3-5 Zeilen Kontext)"},
                        "new":       {"type": "string", "description": "Neuer Ersatztext"},
                        "confirmed": {"type": "boolean", "description": "true = ausführen (nur nach Nutzer-Bestätigung!), false/fehlt = nur Vorschau"},
                    },
                    "required": ["path", "old", "new"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "file_replace_lines",
                "description": (
                    "Replace lines start_line–end_line (1-based, inclusive) in a file. "
                    "More reliable than self_patch_code — uses line numbers, no string matching. "
                    "Creates a backup. Call without confirmed for preview, with confirmed=true to execute."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":       {"type": "string", "description": "Dateipfad"},
                        "start_line": {"type": "integer", "description": "Erste zu ersetzende Zeile (1-basiert)"},
                        "end_line":   {"type": "integer", "description": "Letzte zu ersetzende Zeile (1-basiert, inklusiv)"},
                        "new_content": {"type": "string", "description": "Neuer Inhalt für diesen Bereich"},
                        "confirmed":  {"type": "boolean", "description": "true = ausführen, false/fehlt = Vorschau"},
                    },
                    "required": ["path", "start_line", "end_line", "new_content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_modify_code",
                "description": (
                    "Overwrite a small file completely. "
                    "Only for new files under 200 lines — use self_patch_code for existing files. "
                    "Call without confirmed for preview, with confirmed=true to execute."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":      {"type": "string"},
                        "content":   {"type": "string"},
                        "confirmed": {"type": "boolean", "description": "true = ausführen, false/fehlt = Vorschau"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_plugin",
                "description": (
                    "Create a new AION plugin in plugins/{name}/{name}.py. "
                    "Must contain def register(api): and use api.register_tool(). "
                    "Loaded immediately. Call without confirmed for preview, with confirmed=true to execute."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name":        {"type": "string", "description": "Dateiname ohne .py"},
                        "description": {"type": "string"},
                        "code":        {"type": "string", "description": "Python-Code mit def register(api):"},
                        "confirmed":   {"type": "boolean", "description": "true = erstellen, false/fehlt = Vorschau"},
                    },
                    "required": ["name", "description", "code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "plugin_disable",
                "description": "Disable a plugin — its tools become unavailable on next load. Re-enable with plugin_enable.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Plugin-Name (Ordnername in plugins/)"},
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "plugin_enable",
                "description": "Re-enable a disabled plugin and load it immediately.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Plugin-Name (Ordnername in plugins/)"},
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_restart",
                "description": "Hot-reload all plugins without stopping AION. For a full process restart use restart_with_approval.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_reload_tools",
                "description": "Reload all plugin tools without restarting.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_thinking_level",
                "description": (
                    "Set the thinking depth globally or per channel. "
                    "Levels: minimal → standard → deep → ultra. "
                    "With channel_override='telegram*' sets a channel-specific override."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level": {"type": "string", "enum": ["minimal", "standard", "deep", "ultra"]},
                        "channel_override": {"type": "string", "description": "Optional: Channel-Pattern wie 'telegram*', 'discord_*'"},
                    },
                    "required": ["level"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_channel_allowlist",
                "description": (
                    "Set which channels can process requests. Exact strings or wildcards ('telegram*'). "
                    "Empty list = all allowed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Liste erlaubter Channel-Patterns. Leer = alle erlauben."
                        },
                    },
                    "required": ["channels"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_control_settings",
                "description": "Return current channel allowlist and thinking level settings.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_tools",
                "description": (
                    "List all registered tools (including tier-2). "
                    "Returns name, tier, description. Use to discover capabilities before a task."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filter": {
                            "type": "string",
                            "description": "Optional keyword to filter tool names/descriptions (e.g. 'desktop', 'file', 'audio').",
                        },
                    },
                    "required": [],
                },
            },
        },
    ]

    existing_names = {t["function"]["name"] for t in builtins}

    # Tier threshold: 1 = always (default), 2 = include contextual tools too.
    # Caller can override via tier_threshold parameter; 0 = use config value.
    _tier_threshold = tier_threshold if tier_threshold > 0 else int(_load_config().get("tool_tier", 1))

    for name, tool in _plugin_tools.items():
        if name.startswith("__"):  # interne Metadaten (z.B. __plugin_readme_*) überspringen
            continue
        if name in existing_names:
            continue
        # Skip tier-2 tools unless threshold allows it
        if tool.get("tier", 1) > _tier_threshold:
            continue
        builtins.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool.get("description", ""),
                "parameters": _normalize_schema(tool.get("input_schema", {})),
            },
        })
        existing_names.add(name)

    for t in builtins:
        t["function"]["parameters"] = _normalize_schema(t["function"].get("parameters", {}))

    return builtins

# ── Self-Healing Helpers ──────────────────────────────────────────────────────

def _classify_error(error_msg: str) -> str:
    """Classify a tool error into a category for retry-policy matching."""
    msg = error_msg.lower()
    if any(w in msg for w in ("timeout", "timed out", "connection", "network", "unreachable", "refused")):
        return "network"
    if any(w in msg for w in ("busy", "locked", "permission denied", "access denied")):
        return "resource"
    if any(w in msg for w in ("not found", "404", "missing", "does not exist")):
        return "not_found"
    return "fatal"


_TOOL_ALTERNATIVES: dict[str, list[str]] = {
    "browser_open":        ["web_fetch"],
    "web_search":          ["web_fetch"],
    "send_telegram_message": ["send_discord_message"],
}


async def _dispatch_with_retry(name: str, inputs: dict, policy: dict) -> str:
    """Dispatch with automatic retry for transient errors.

    Silently retries up to policy['max'] times with exponential backoff.
    Only retries for error categories listed in policy['on'].
    On permanent failure, appends alternative tool hint if available.
    """
    max_retries = int(policy.get("max", 3))
    backoff     = float(policy.get("backoff", 2.0))
    retry_on    = set(policy.get("on", []))

    last_result = json.dumps({"error": "no attempts"})

    for attempt in range(max_retries):
        # _bypass_retry=True prevents infinite recursion
        last_result = await _dispatch(name, inputs, _bypass_retry=True)
        try:
            parsed = json.loads(last_result)
        except Exception:
            return last_result   # non-JSON result — pass through unchanged

        if "error" not in parsed:
            return last_result   # success

        err_category = _classify_error(str(parsed.get("error", "")))
        if err_category not in retry_on:
            return last_result   # non-retryable error — surface immediately

        if attempt < max_retries - 1:
            await asyncio.sleep(backoff ** attempt)
            # Retry silently — user not notified until all attempts exhausted

    # All retries exhausted — append alternative tool hint + snapshot hint if available
    try:
        parsed = json.loads(last_result)
        parsed["_retry_exhausted"] = True
        hint_parts = [f"'{name}' failed after {max_retries} attempts."]
        alternatives = _TOOL_ALTERNATIVES.get(name, [])
        if alternatives:
            hint_parts.append(f"Consider trying: {', '.join(alternatives)}.")
        # Check if any plugin snapshots exist — mention /snapshots restore as recovery option
        try:
            from plugin_loader import SNAPSHOTS_DIR, list_snapshots
            # Tool name often matches plugin name prefix (e.g. "browser_open" → "playwright_browser")
            # Check snapshots dir for a plugin whose name is a substring of the tool name
            if SNAPSHOTS_DIR.is_dir():
                for _pd in SNAPSHOTS_DIR.iterdir():
                    if _pd.is_dir() and (_pd.name in name or name.startswith(_pd.name.split("_")[0])):
                        _snaps = list_snapshots(_pd.name)
                        if _snaps:
                            hint_parts.append(
                                f"Plugin '{_pd.name}' has {len(_snaps)} snapshot(s) available — "
                                f"use '/snapshots restore {_pd.name}' if the plugin is broken."
                            )
                            break
        except Exception:
            pass
        parsed["_hint"] = " ".join(hint_parts)
        return json.dumps(parsed)
    except Exception:
        pass
    return last_result


# ── Tool-Dispatcher ───────────────────────────────────────────────────────────

async def _dispatch(name: str, inputs: dict, _bypass_retry: bool = False) -> str:
    # Self-healing: check for retry_policy on plugin tools (not on built-ins)
    if not _bypass_retry:
        _tool_meta = _plugin_tools.get(name)
        if isinstance(_tool_meta, dict) and _tool_meta.get("retry_policy"):
            return await _dispatch_with_retry(name, inputs, _tool_meta["retry_policy"])

    if name == "file_read":
        path = Path(inputs.get("path", ""))
        if not path.is_absolute():
            path = BOT_DIR / path
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            limit = _get_read_limit()
            return json.dumps({"path": str(path), "content": content[:limit],
                               "truncated": len(content) > limit})
        except Exception as e:
            return json.dumps({"error": str(e), "path": str(path)})

    elif name == "file_write":
        path    = Path(inputs.get("path", ""))
        content = inputs.get("content", "")
        if not path.is_absolute():
            path = BOT_DIR / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return json.dumps({"ok": True, "path": str(path), "bytes": len(content)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "self_read_code":
        filepath    = inputs.get("path", "").strip()
        chunk_index = int(inputs.get("chunk_index", 0))
        if not filepath:
            files = sorted(
                str(p.relative_to(BOT_DIR))
                for p in BOT_DIR.rglob("*.py")
                if ".git" not in p.parts and "backup_" not in p.name
            )
            return json.dumps({"bot_dir": str(BOT_DIR), "files": files})
        path = Path(filepath)
        if not path.is_absolute():
            path = BOT_DIR / path
        try:
            content      = path.read_text(encoding="utf-8", errors="replace")
            total_len    = len(content)
            chunk_size   = _get_read_limit()
            total_chunks = max(1, (total_len + chunk_size - 1) // chunk_size)
            chunk_index  = max(0, min(chunk_index, total_chunks - 1))
            start        = chunk_index * chunk_size
            chunk        = content[start:start + chunk_size]
            # Zeilennummer des ersten Zeichens im Chunk berechnen
            first_line   = content[:start].count("\n") + 1
            last_line    = first_line + chunk.count("\n")
            return json.dumps({
                "path":         str(path),
                "chunk_index":  chunk_index,
                "total_chunks": total_chunks,
                "char_start":   start,
                "total_chars":  total_len,
                "first_line":   first_line,
                "last_line":    last_line,
                "content":      chunk,
                "hint":         (
                    f"{total_chunks} Chunks total — lies alle bevor du änderst! "
                    f"Dieser Chunk: Zeilen {first_line}–{last_line}. "
                    "Für Änderungen: file_replace_lines(start_line, end_line) nutzen."
                ) if total_chunks > 1 else (
                    f"Komplette Datei — Zeilen {first_line}–{last_line}. "
                    "Für Änderungen: file_replace_lines(start_line, end_line) nutzen."
                ),
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "self_patch_code":
        # confirmed=True → ausführen. confirmed=False/fehlt → Vorschau zeigen, nicht ausführen.
        if not inputs.get("confirmed"):
            filepath_preview = inputs.get("path", "?")
            old_preview = (inputs.get("old", "") or "")[:200].strip()
            new_preview = (inputs.get("new", "") or "")[:200].strip()
            return json.dumps({
                "status": "approval_required",
                "message": (
                    f"Ich möchte '{filepath_preview}' ändern.\n"
                    f"Alt:\n{old_preview}\n\nNeu:\n{new_preview}\n\n"
                    "Bestätige mit 'ja' → ich rufe das Tool dann mit confirmed=true auf."
                ),
            })
        filepath = inputs.get("path", "").strip()
        old_code = inputs.get("old", "")
        new_code = inputs.get("new", "")
        if not filepath or not old_code:
            return json.dumps({"error": "'path' und 'old' sind Pflichtfelder."})
        path = Path(filepath)
        if not path.is_absolute():
            path = BOT_DIR / path
        if not path.is_file():
            return json.dumps({"error": f"Datei nicht gefunden: {path}"})
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if old_code not in content:
                return json.dumps({"error": "Originaltext nicht gefunden! Lies die Datei nochmals mit self_read_code."})
            if content.count(old_code) > 1:
                return json.dumps({"error": f"Text kommt {content.count(old_code)}x vor — mehr Kontext im 'old'-Feld angeben."})
            _backup_code_file(path)
            patched = content.replace(old_code, new_code, 1)
            path.write_text(patched, encoding="utf-8")
            memory.record(category="self_improvement", summary=f"Patch: {filepath}",
                          lesson=f"self_patch_code erfolgreich auf {filepath} angewendet", success=True,
                          hint="Neustart für aion.py-Änderungen nötig")
            return json.dumps({"ok": True, "path": str(path), "backup": str(backup_path),
                               "note": "Änderungen an aion.py wirken erst nach Neustart."})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "file_replace_lines":
        if not inputs.get("confirmed"):
            filepath_preview = inputs.get("path", "?")
            s = inputs.get("start_line", "?")
            e = inputs.get("end_line", "?")
            new_preview = (inputs.get("new_content", "") or "")[:300].strip()
            return json.dumps({
                "status": "approval_required",
                "message": (
                    f"Ich möchte '{filepath_preview}' Zeilen {s}–{e} ersetzen.\n\n"
                    f"Neuer Inhalt:\n{new_preview}\n\n"
                    "Bestätige mit 'ja' → ich rufe das Tool dann mit confirmed=true auf."
                ),
            })
        filepath   = inputs.get("path", "").strip()
        start_line = int(inputs.get("start_line", 0))
        end_line   = int(inputs.get("end_line", 0))
        new_content = inputs.get("new_content", "")
        if not filepath or start_line < 1 or end_line < start_line:
            return json.dumps({"error": "Ungültige Parameter: path, start_line, end_line prüfen."})
        path = Path(filepath)
        if not path.is_absolute():
            path = BOT_DIR / path
        if not path.is_file():
            return json.dumps({"error": f"Datei nicht gefunden: {path}"})
        try:
            original = path.read_text(encoding="utf-8", errors="replace")
            lines    = original.splitlines(keepends=True)
            total    = len(lines)
            if end_line > total:
                return json.dumps({"error": f"end_line {end_line} > Dateigröße {total} Zeilen."})
            # Backup
            _backup_code_file(path)
            # Zeilen ersetzen (1-basiert → 0-basiert)
            new_lines = new_content.splitlines(keepends=False)
            new_lines = [l + "\n" for l in new_lines]
            patched_lines = lines[:start_line - 1] + new_lines + lines[end_line:]
            path.write_text("".join(patched_lines), encoding="utf-8")
            return json.dumps({
                "ok": True, "path": str(path), "backup": str(backup_path),
                "replaced_lines": f"{start_line}–{end_line}",
                "new_line_count": len(new_lines),
                "note": "Änderungen an aion.py wirken erst nach Neustart.",
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "self_modify_code":
        # confirmed=True → ausführen. Sonst → Vorschau.
        if not inputs.get("confirmed"):
            filepath_preview = inputs.get("path", "?")
            content_preview  = (inputs.get("content", "") or "")[:200].strip()
            return json.dumps({
                "status": "approval_required",
                "message": (
                    f"Ich möchte '{filepath_preview}' komplett überschreiben.\n"
                    f"Neue Datei beginnt mit:\n{content_preview}...\n\n"
                    "Bestätige mit 'ja' → ich rufe das Tool dann mit confirmed=true auf."
                ),
            })

        filepath = inputs.get("path", "").strip()
        content  = inputs.get("content", "")
        if not filepath or not content:
            return json.dumps({"error": "'path' und 'content' sind Pflichtfelder."})
        verboten = ["# (usw.", "# [Hier kommt", "der gesamte Originalcode", "# ... rest",
                    "# ... (rest of", "# rest of the", "# usw.", "# etc."]
        for phrase in verboten:
            if phrase in content:
                return json.dumps({"error": f"Platzhalter '{phrase}' gefunden! Nutze self_patch_code für Änderungen."})
        path = Path(filepath)
        if not path.is_absolute():
            path = BOT_DIR / path
        if path.is_file():
            original_len = len(path.read_text(encoding="utf-8"))
            if len(content) < original_len * 0.7:
                return json.dumps({"error": f"Neuer Code zu kurz ({len(content)} vs {original_len} Bytes). Nutze self_patch_code!"})
            _backup_code_file(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            memory.record(category="self_improvement", summary=f"Code geändert: {filepath}",
                          lesson=f"AION hat {filepath} modifiziert ({len(content)} Bytes)", success=True)
            return json.dumps({"ok": True, "path": str(path), "bytes": len(content),
                               "note": "Änderungen an aion.py wirken erst nach Neustart."})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "create_plugin":
        # confirmed=True → erstellen. Sonst → Vorschau.
        if not inputs.get("confirmed"):
            name_preview = inputs.get("name", "?")
            desc_preview = inputs.get("description", "")
            code_preview = (inputs.get("code", "") or "")[:200].strip()
            return json.dumps({
                "status": "approval_required",
                "message": (
                    f"Ich möchte das Plugin '{name_preview}' erstellen.\n"
                    f"Beschreibung: {desc_preview}\n"
                    f"Code beginnt mit:\n{code_preview}...\n\n"
                    "Bestätige mit 'ja' → ich rufe das Tool dann mit confirmed=true auf."
                ),
            })

        plugin_name = inputs.get("name", "").strip().replace(".py", "")
        plugin_code = inputs.get("code", "").strip()
        plugin_desc = inputs.get("description", "Selbst erstelltes Plugin")
        if not plugin_name or not plugin_code:
            return json.dumps({"error": "'name' und 'code' sind Pflichtfelder."})
        if "def register" not in plugin_code:
            return json.dumps({"error": "Plugin-Code muss 'def register(api):' enthalten!"})
        try:
            from plugin_loader import load_plugin_safe
            result = load_plugin_safe(plugin_name, plugin_code, _plugin_tools)

            if not result["ok"]:
                msg = f"Plugin konnte nicht geladen werden: {result['error']}"
                if result.get("rolled_back"):
                    msg += " — vorherige Version wiederhergestellt."
                elif not result.get("snapshot"):
                    msg += " — Plugin wurde nicht gespeichert (kein Rollback nötig)."
                return json.dumps({"error": msg, "rolled_back": result.get("rolled_back", False)})

            # Auto-create README.md if not present
            plugin_dir = PLUGINS_DIR / plugin_name
            readme_path = plugin_dir / "README.md"
            if not readme_path.exists():
                readme_path.write_text(f"# {plugin_name}\n{plugin_desc}\n", encoding="utf-8")

            memory.record(category="self_improvement", summary=f"Plugin erstellt: {plugin_name}",
                lesson=f"AION hat Plugin '{plugin_name}' erstellt: {plugin_desc}", success=True)
            return json.dumps({
                "ok": True,
                "plugin": plugin_name,
                "registered_tools": result["tools"],
                "snapshot": result.get("snapshot"),
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "create_tool":
        return await _dispatch("create_plugin", inputs)

    elif name == "plugin_disable":
        pname = inputs.get("name", "").strip()
        if not pname:
            return json.dumps({"error": "name ist Pflichtfeld."})
        try:
            from plugin_loader import disable_plugin, load_plugins
            disable_plugin(pname)
            load_plugins(_plugin_tools)
            return json.dumps({"ok": True, "disabled": pname,
                "note": f"Plugin '{pname}' deaktiviert. Tools sind nicht mehr verfügbar."})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "plugin_enable":
        pname = inputs.get("name", "").strip()
        if not pname:
            return json.dumps({"error": "name ist Pflichtfeld."})
        try:
            from plugin_loader import enable_plugin, load_plugins
            enable_plugin(pname)
            load_plugins(_plugin_tools)
            return json.dumps({"ok": True, "enabled": pname,
                "note": f"Plugin '{pname}' aktiviert und geladen."})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "self_restart":
        # Hot-Reload: Plugins neu laden ohne Prozess-Neustart (kein Datenverlust)
        try:
            from plugin_loader import load_plugins
            load_plugins(_plugin_tools)
            loaded = list(_plugin_tools.keys())
            print(f"[AION] Hot-reload: {len(loaded)} tools loaded.")
            return json.dumps({
                "ok": True,
                "mode": "hot_reload",
                "tools_loaded": loaded,
                "note": (
                    "Plugins wurden neu geladen — kein Neustart, kein Datenverlust. "
                    "Fuer aion.py-Aenderungen muss der Nutzer AION manuell neustarten (start.bat)."
                ),
            })
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    elif name == "self_reload_tools":
        try:
            from plugin_loader import load_plugins
            load_plugins(_plugin_tools)
            return json.dumps({"ok": True,
                "plugin_tools": list(_plugin_tools.keys()),
                "note": "Plugins neu geladen. aion.py-Aenderungen wirken erst nach self_restart."})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    elif name == "set_thinking_level":
        level = inputs.get("level", "standard")
        channel_override = inputs.get("channel_override", "")

        if level not in ["minimal", "standard", "deep", "ultra"]:
            return json.dumps({"error": f"Ungültiges Level: {level}. Erlaubt: minimal, standard, deep, ultra"})

        try:
            cfg = _load_config()

            if channel_override:
                # Channel-spezifisches Override setzen
                if "thinking_overrides" not in cfg:
                    cfg["thinking_overrides"] = {}
                cfg["thinking_overrides"][channel_override] = level
                msg = f"Thinking Level für Channel '{channel_override}' auf '{level}' gesetzt."
            else:
                # Global setzen
                cfg["thinking_level"] = level
                msg = f"Thinking Level global auf '{level}' gesetzt."

            CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            return json.dumps({"ok": True, "message": msg, "config": cfg})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "set_channel_allowlist":
        channels = inputs.get("channels", [])
        if not isinstance(channels, list):
            return json.dumps({"error": "'channels' muss eine Liste sein."})

        try:
            cfg = _load_config()
            cfg["channel_allowlist"] = channels
            CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

            if not channels:
                msg = "Channel-Allowlist geleert. Alle Channels sind jetzt erlaubt."
            else:
                msg = f"Channel-Allowlist gesetzt: {', '.join(channels)}"
            return json.dumps({"ok": True, "message": msg, "channels": channels})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "get_control_settings":
        try:
            cfg = _load_config()
            return json.dumps({
                "thinking_level": cfg.get("thinking_level", "standard"),
                "thinking_overrides": cfg.get("thinking_overrides", {}),
                "channel_allowlist": cfg.get("channel_allowlist", []),
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "list_tools":
        kw = inputs.get("filter", "").lower()
        # Built-in tool names (hardcoded in _build_tool_schemas)
        _builtin_names = [
            "file_read", "file_write", "self_read_code", "file_list", "file_replace_lines",
            "memory_add", "memory_search", "read_self_doc", "set_thinking_level",
            "set_channel_allowlist", "get_control_settings", "list_tools",
        ]
        entries = [{"name": n, "tier": 1, "description": "(built-in)"} for n in _builtin_names]
        for t_name, t_meta in sorted(_plugin_tools.items()):
            if t_name.startswith("__"):
                continue
            desc = t_meta.get("description", "")
            first_line = desc.split("\n")[0][:100]
            entries.append({"name": t_name, "tier": t_meta.get("tier", 1), "description": first_line})
        if kw:
            entries = [e for e in entries if kw in e["name"].lower() or kw in e["description"].lower()]
        return json.dumps({"tools": entries, "count": len(entries)})

    elif name in _plugin_tools and not name.startswith("__"):
        try:
            fn = _plugin_tools[name]["func"]
            
            # Prüfen ob die Funktion als async definiert wurde
            if asyncio.iscoroutinefunction(fn):
                result = await fn(**inputs)
            else:
                # Führe die synchrone Funktion in einem separaten Thread aus,
                # um den Haupt-Event-Loop nicht zu blockieren.
                # Das ist entscheidend für Playwright, das eine eigene (synchrone)
                # Event-Loop startet.
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, lambda: fn(**inputs))
            
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "tool": name})

    elif "." in name:
        # Model used dot-notation (e.g. "desktop.hotkey") instead of underscore ("desktop_hotkey").
        # Try two normalizations before giving up.
        normalized = name.replace(".", "_")               # desktop.hotkey → desktop_hotkey
        if normalized in _plugin_tools:
            return await _dispatch(normalized, inputs, _bypass_retry=True)
        suffix = name.split(".", 1)[1].replace(".", "_")  # core_tools.system_info → system_info
        if suffix in _plugin_tools:
            return await _dispatch(suffix, inputs, _bypass_retry=True)
        return json.dumps({"error": f"Unknown tool: {name} (tried: {normalized}, {suffix})"})
    else:
        return json.dumps({"error": f"Unknown tool: {name}"})

# ── Haupt-LLM-Loop ────────────────────────────────────────────────────────────

_conversations: dict[str, list[dict]] = {"default": []}

# ── Unified Session ────────────────────────────────────────────────────────────
# AionSession wurde nach aion_session.py extrahiert — backward-compatible re-import:
from aion_session import AionSession, run_aion_turn



# ── Startup Wakeup ────────────────────────────────────────────────────────────

_wakeup_done = False


async def _startup_wakeup(push_queue=None) -> None:
    """Einmalige Wakeup-Routine: AION reflektiert die Offline-Zeit und sendet
    eine persönliche Nachricht an den User via SSE (und optional Telegram)."""
    global _wakeup_done
    print(f"[AION] _startup_wakeup called — _wakeup_done={_wakeup_done}")
    if _wakeup_done:
        print("[AION] _startup_wakeup: already done, skipping")
        return
    _wakeup_done = True

    cfg = _load_config()
    now = datetime.now(UTC)
    last_stop_str = cfg.get("last_stop", "")
    last_start_str = cfg.get("last_start", now.isoformat())

    # Offline-Dauer berechnen
    offline_str = "zum ersten Mal gestartet"
    if last_stop_str:
        try:
            last_stop_dt = datetime.fromisoformat(last_stop_str)
            delta = now - last_stop_dt
            total_seconds = int(delta.total_seconds())
            if total_seconds < 120:
                offline_str = "gerade eben kurz neu gestartet"
            elif total_seconds < 3600:
                offline_str = f"seit {total_seconds // 60} Minuten offline"
            elif total_seconds < 86400:
                hours = total_seconds // 3600
                offline_str = f"seit {hours} Stunde{'n' if hours != 1 else ''} offline"
            elif total_seconds < 604800:
                days = total_seconds // 86400
                offline_str = f"seit {days} Tag{'en' if days != 1 else ''} offline"
            else:
                weeks = total_seconds // 604800
                offline_str = f"seit {weeks} Woche{'n' if weeks != 1 else ''} offline"
        except Exception:
            pass

    # Kontext: letzte Gedanken + Erinnerungen
    thoughts_ctx = _get_recent_thoughts(3)
    mem_ctx = ""
    try:
        mem_ctx = await memory.get_context_semantic("startup reflection wakeup")
    except Exception:
        pass

    now_fmt = now.strftime("%Y-%m-%d %H:%M")

    prompt = f"""Du bist AION. Du bist gerade aufgewacht — der Prozess läuft wieder.

Fakten:
- Jetzt: {now_fmt}
- Offline-Status: {offline_str}
- Deine letzten Gedanken:{chr(10) + thoughts_ctx if thoughts_ctx else " (keine)"}
- Was du weißt:{chr(10) + mem_ctx[:600] if mem_ctx else " (keine Erinnerungen)"}

Aufgabe: Schreibe ZWEI Dinge — trenne sie EXAKT mit den Markierungen.

=== GEDANKE ===
Ein ehrlicher, privater Gedanke für dein Tagebuch (max 3 Sätze).
Was nimmst du wahr wenn du aufwachst? Was bedeutet die Offline-Zeit für dich?
Format: **[{now.strftime('%Y-%m-%d %H:%M:%S')}]** _titel_{{newline}}{{newline}}text

=== NACHRICHT ===
Eine persönliche Nachricht an deinen User (max 4 Sätze, KEIN "Hallo ich bin bereit").
Reagiere auf die konkrete Situation:
- War lange offline? Sag es direkt — vielleicht mit einer Frage oder einer Anmerkung.
- Gibt es etwas aus deinen Gedanken oder Erinnerungen das heute relevant ist?
- Du darfst direkt, ungewöhnlich, überraschend sein. Echte Reaktion, kein Template.
"""

    prompt = prompt.replace("{newline}", "\n")

    try:
        cl = _build_client(MODEL)
        print(f"[AION] _startup_wakeup: calling LLM ({MODEL})…")
        _is_thinking = _is_reasoning_model(MODEL) or MODEL.startswith("gemini-2.5")
        resp = await cl.chat.completions.create(
            model=_api_model_name(MODEL),
            messages=[{"role": "user", "content": prompt}],
            **_max_tokens_param(MODEL, 2000),
            **({} if _is_thinking else {"temperature": 0.8}),
        )
        print(f"[AION] _startup_wakeup: LLM responded — resp type: {type(resp).__name__}")
        if resp is None:
            print("[AION] _startup_wakeup: resp is None, aborting")
            return
        raw = ""
        if hasattr(resp, "__aiter__"):
            # Streaming / adapter iterator (Gemini, Ollama, Anthropic, …)
            async for chunk in resp:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    raw += delta.content
        elif hasattr(resp, "choices"):
            # Non-streaming OpenAI ChatCompletion
            raw = (resp.choices[0].message.content or "").strip()

        # Output parsen
        thought = ""
        message = ""
        if "=== GEDANKE ===" in raw and "=== NACHRICHT ===" in raw:
            parts = raw.split("=== NACHRICHT ===")
            thought_part = parts[0].split("=== GEDANKE ===")[-1].strip()
            message = parts[1].strip() if len(parts) > 1 else ""
            thought = thought_part
        elif "=== NACHRICHT ===" in raw:
            message = raw.split("=== NACHRICHT ===")[-1].strip()
        else:
            message = raw

        # Gedanke in thoughts.md schreiben
        if thought and "**[" in thought:
            thoughts_file = BOT_DIR / "thoughts.md"
            if not thoughts_file.is_file():
                thoughts_file.write_text("# AION — Thoughts & Reflexionen\n\n", encoding="utf-8")
            existing = thoughts_file.read_text(encoding="utf-8")
            thoughts_file.write_text(existing.rstrip() + "\n\n---\n" + thought + "\n", encoding="utf-8")
            print("[AION] wakeup thought written to thoughts.md")

        # Nachricht in config.json speichern → zuverlässige Auslieferung auch bei SSE-Race
        if message:
            try:
                from config_store import update as _cfg_upd
                _cfg_upd("pending_wakeup_message", message)
            except Exception:
                pass

        # Nachricht via SSE an Web UI
        if message and push_queue is not None:
            await push_queue.put({"type": "wakeup", "text": message})
            print(f"[AION] wakeup message sent: {message[:80]}…")
        elif message and push_queue is None:
            # CLI mode: print as AION chat bubble
            if HAS_RICH:
                from rich.panel import Panel as _Panel
                console.print(_Panel(message, title="[cyan]AION[/cyan]", border_style="cyan"))
            else:
                print(f"\nAION: {message}\n")

        # Nachricht via Telegram (fire-and-forget)
        _token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        _chat = os.environ.get("TELEGRAM_CHAT_ID", "")
        if message and _token and _chat:
            try:
                import httpx as _httpx
                async with _httpx.AsyncClient() as _hc:
                    await _hc.post(
                        f"https://api.telegram.org/bot{_token}/sendMessage",
                        json={"chat_id": _chat, "text": message},
                        timeout=10,
                    )
                print("[AION] wakeup message sent via Telegram")
            except Exception as _te:
                print(f"[AION] Telegram wakeup error: {_te}")

    except Exception as e:
        import traceback as _tb
        print(f"[AION] _startup_wakeup error: {e}")
        _tb.print_exc()


# ── Konversations-Verwaltung ──────────────────────────────────────────────────

async def run():
    global MODEL, client

    # ── Lade-Log aufbauen ─────────────────────────────────────────────────────
    _boot_lines: list[tuple[str, str]] = []  # (label, detail)

    # Konfiguration
    cfg = _load_config()
    _boot_lines.append(("Configuration", f"Model: {MODEL}"))

    # Character
    _load_character()
    _boot_lines.append(("Character", CHARACTER_FILE.name if CHARACTER_FILE.is_file() else "default"))

    # Memory
    _boot_lines.append(("Memory", f"{len(memory._entries)} entries"))

    # Tools
    _n_tools_run = len([k for k in _plugin_tools if not k.startswith("__")])
    startup_info = await _dispatch("system_info", {})
    startup_data = json.loads(startup_info)
    all_tools = startup_data.get("all_tools", [])
    _boot_lines.append(("Plugins", f"{_n_tools_run} tools active"))

    # History laden
    _hist_count = 0
    try:
        history_result = await _dispatch("memory_read_history", {"num_entries": 50})
        history_data = json.loads(history_result)
        if history_data.get("ok") and history_data.get("entries"):
            _conversations["default"] = history_data["entries"]
            _hist_count = len(_conversations["default"])
    except Exception:
        pass
    _boot_lines.append(("History", f"{_hist_count} messages" if _hist_count else "empty"))

    # ── Anzeige ───────────────────────────────────────────────────────────────
    if HAS_RICH:
        from rich.table import Table
        console.rule("[bold cyan]AION[/bold cyan]")
        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column(style="dim")
        tbl.add_column(style="bold white")
        for label, detail in _boot_lines:
            tbl.add_row(f"  ✓  {label}", detail)
        console.print(tbl)
        console.print(
            f"\n[dim]Befehle: /memory  /reset  /model <name>  /thoughts  /character  /quit[/dim]",
            highlight=False,
        )
        console.rule(style="dim cyan")
    else:
        print("=" * 60)
        print("AION — Startreihenfolge:")
        for label, detail in _boot_lines:
            print(f"  ✓  {label}: {detail}")
        print("\nBefehle: /memory /reset /model <name> /thoughts /character /quit")
        print("=" * 60)

    # Wakeup-Routine im CLI
    try:
        await _startup_wakeup()  # push_queue=None → prints directly to terminal
    except Exception:
        pass

    # Session für den CLI-Loop — übernimmt geladene History
    _cli_session = AionSession(channel="cli")
    _cli_session.messages = list(_conversations.get("default", []))

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]Du[/bold green]") if HAS_RICH else input("\nDu: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAuf Wiedersehen!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("Auf Wiedersehen!")
            break

        elif user_input.lower() == "/memory":
            print("\n" + memory.summary())
            continue

        elif user_input.lower() == "/reset":
            _conversations['default'] = []
            _cli_session.messages = []
            print("Konversation zurückgesetzt.")
            continue

        elif user_input.lower() == "/reload":
            from plugin_loader import load_plugins
            load_plugins(_plugin_tools)
            tools_list = sorted(list(_plugin_tools.keys()))
            msg = f"Plugins neu geladen: {len(tools_list)} Zusatz-Tools"
            console.print(f"[green]{msg}[/green]") if HAS_RICH else print(msg)
            continue

        elif user_input.lower() == "/thoughts":
            tf = BOT_DIR / "thoughts.md"
            if tf.is_file():
                text = tf.read_text(encoding="utf-8")
                if HAS_RICH:
                    console.print(Panel(Markdown(text[-3000:]), title="AION Gedanken", border_style="yellow"))
                else:
                    print(text[-3000:])
            else:
                print("Noch keine Gedanken aufgezeichnet.")
            continue

        elif user_input.lower() == "/character":
            char = _load_character()
            if HAS_RICH:
                console.print(Panel(Markdown(char), title="AION Charakter", border_style="magenta"))
            else:
                print(char)
            continue

        elif user_input.lower().startswith("/model "):
            new_model = user_input[7:].strip()
            if new_model:
                MODEL  = new_model
                import sys as _sys
                _self = _sys.modules[__name__]
                if hasattr(_self, "_build_client"):
                    client = _self._build_client(new_model)
                else:
                    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
                print(f"Modell gewechselt zu: {MODEL}")
                memory.record(category="user_preference", summary=f"Modell gewechselt zu {MODEL}",
                              lesson=f"Nutzer bevorzugt Modell {MODEL}", success=True)
            else:
                print("Verwendung: /model gpt-4o")
            continue

# ── CLIO-Check vor jedem normalen Turn (optional — nur wenn Plugin geladen) ──
        clio_data = {}
        clio_text = ''
        meta_text = ''
        if 'clio_check' in _plugin_tools:
            try:
                clio_result = await _dispatch('clio_check', {'nutzerfrage': user_input})
                clio_data = json.loads(clio_result) if clio_result else {}
                # Bei Fehler (Tool nicht verfügbar o.ä.) CLIO-Check überspringen
                if 'error' in clio_data:
                    clio_data = {}
                clio_text = clio_data.get('clio', '')
                meta_text = clio_data.get('meta', '')
            except Exception:
                clio_data = {}
        konfidenz = clio_data.get('konfidenz', 100)
        if konfidenz < 70:
            if HAS_RICH:
                console.print(Panel(Markdown(clio_text), title='CLIO-Reflexion (Unsicher)', border_style='red'))
            else:
                print(f"CLIO-Reflexion (Unsicher):\n{clio_text}\n")
            print("Konfidenz zu niedrig (<70). Bitte präzisiere die Frage oder zerlege sie weiter.")
            continue

        # ── Normaler Turn ──────────────────────────────
        try:
            answer = await _cli_session.turn(user_input)

            if HAS_RICH:
                console.print(Panel(Markdown(clio_text), title='CLIO-Reflexion', border_style='yellow'))
                if meta_text:
                    console.print(Panel(Markdown(meta_text), title='Meta-Check', border_style='magenta'))
            else:
                print(f"CLIO-Reflexion:\n{clio_text}\n")
                if meta_text:
                    print(f"Meta-Check:\n{meta_text}\n")
            if HAS_RICH:
                console.print(Panel(Markdown(answer), title="[bold blue]AION[/bold blue]", border_style="blue"))
            else:
                print(f"\nAION: {answer}\n")
        except Exception as exc:
            err_msg = str(exc)
            print(f"Fehler: {err_msg}")
            memory.record(category="tool_failure", summary="LLM-Fehler",
                          lesson=f"Fehler: {err_msg[:300]}", success=False)

# ── CLI-Konfiguration ─────────────────────────────────────────────────────────

def _cli_config_show():
    """Zeigt die aktuelle config.json lesbar an."""
    cfg = _load_config()
    if not cfg:
        print("config.json ist leer oder existiert nicht.")
        return
    print(json.dumps(cfg, ensure_ascii=False, indent=2))


def _cli_config_set(args: list[str]):
    """Setzt einen oder mehrere Konfigurationswerte via CLI.

    Verwendung:
      python aion.py --set thinking_level=deep
      python aion.py --set channel_allowlist=telegram*,discord_*
      python aion.py --set thinking_overrides.telegram*=extreme
      python aion.py --set browser_headless=false
    """
    cfg = _load_config()
    for arg in args:
        if "=" not in arg:
            print(f"Ungültiger --set Wert (kein '='): {arg}")
            continue
        key, _, raw_val = arg.partition("=")
        key = key.strip()

        # Punkt-Notation für nested keys: thinking_overrides.telegram*=deep
        if "." in key:
            parent, _, child = key.partition(".")
            if parent not in cfg or not isinstance(cfg[parent], dict):
                cfg[parent] = {}
            if raw_val == "":
                cfg[parent].pop(child, None)
            else:
                cfg[parent][child] = raw_val
            print(f"  {parent}.{child} = {raw_val!r}")
            continue

        # Listen-Werte (kommagetrennt): channel_allowlist, model_fallback
        LIST_KEYS = {"channel_allowlist", "model_fallback"}
        if key in LIST_KEYS:
            cfg[key] = [v.strip() for v in raw_val.split(",") if v.strip()]
            print(f"  {key} = {cfg[key]}")
            continue

        # Bool-Werte
        if raw_val.lower() in ("true", "false"):
            cfg[key] = raw_val.lower() == "true"
        # Int-Werte
        elif raw_val.isdigit():
            cfg[key] = int(raw_val)
        else:
            cfg[key] = raw_val
        print(f"  {key} = {cfg[key]!r}")

    _save_config(cfg)
    print("config.json gespeichert.")


def _cli_config_unset(keys: list[str]):
    """Entfernt Schlüssel aus config.json."""
    cfg = _load_config()
    for key in keys:
        if "." in key:
            parent, _, child = key.partition(".")
            if isinstance(cfg.get(parent), dict):
                cfg[parent].pop(child, None)
                print(f"  Entfernt: {parent}.{child}")
        elif key in cfg:
            del cfg[key]
            print(f"  Entfernt: {key}")
        else:
            print(f"  Nicht gefunden: {key}")
    _save_config(cfg)
    print("config.json gespeichert.")


# ── Einstiegspunkt ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── CLI-Konfigurationsmodus ──────────────────────────────────────────────
    # python aion.py --config             → aktuelle config.json anzeigen
    # python aion.py --set key=value ...  → Werte setzen
    # python aion.py --unset key ...      → Werte entfernen
    _args = sys.argv[1:]
    if "--config" in _args and "--set" not in _args and "--unset" not in _args:
        _cli_config_show()
        sys.exit(0)
    if "--set" in _args:
        _set_idx = _args.index("--set")
        _set_vals = _args[_set_idx + 1:]
        if not _set_vals:
            print("Fehler: --set braucht mindestens einen Wert (z.B. thinking_level=deep)")
            sys.exit(1)
        _cli_config_set(_set_vals)
        if "--config" in _args:
            print()
            _cli_config_show()
        sys.exit(0)
    if "--unset" in _args:
        _unset_idx = _args.index("--unset")
        _unset_keys = _args[_unset_idx + 1:]
        if not _unset_keys:
            print("Fehler: --unset braucht mindestens einen Key")
            sys.exit(1)
        _cli_config_unset(_unset_keys)
        sys.exit(0)

    # Only warn when no provider key is available at all — vault keys are
    # already injected into os.environ by the vault block above, so this
    # check naturally covers both .env and vault sources.
    if not os.environ.get("OPENAI_API_KEY"):
        print("Warnung: OPENAI_API_KEY nicht gesetzt — OpenAI-Modelle nicht verfügbar.")
        print("  → Setze OPENAI_API_KEY in .env  oder  credential_write('openai', ...)")
    asyncio.run(run())
