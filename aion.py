if "__file__" not in globals(): __file__ = __import__("os").path.abspath("aion.py")

"""
AION — Autonomous Intelligent Operations Node
=============================================
"""

import asyncio
import contextvars
import importlib.util
import json
import os
import platform
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

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
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


def _build_client(model: str):
    """Build an LLM client for model. Checks provider registry first, falls back to OpenAI."""
    for entry in _provider_registry:
        if model.startswith(entry["prefix"]):
            try:
                return entry["build_fn"](model)
            except Exception as e:
                print(f"[AION] Provider '{entry['label']}' failed for '{model}': {e}")
    # Default: OpenAI
    return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


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
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.is_file() else {}
        perms = cfg.get("permissions", {})
        return {k: perms.get(k, v) for k, v in PERMISSION_DEFAULTS.items()}
    except Exception:
        return dict(PERMISSION_DEFAULTS)

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


# ── Channel Allowlist (Security) ────────────────────────────────────────────────

def _check_channel_allowlist(channel: str) -> tuple[bool, str]:
    """Checks if a channel is allowed on the allowlist.

    Returns: (is_allowed, message)
    - Wenn channel_allowlist nicht gesetzt: alle Channels erlaubt
    - Wenn gesetzt: nur Channels in der Liste erlaubt
    - Wildcards: "telegram*", "discord*", "web*" possible
    """
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.is_file() else {}
        allowlist = cfg.get("channel_allowlist", [])

        # Wenn leer oder nicht gesetzt: alles erlaubt
        if not allowlist:
            return True, ""

        # Check exact match or wildcard match
        for pattern in allowlist:
            if isinstance(pattern, str):
                # Wildcard: "telegram*" matcht "telegram_123", "telegram_456"
                if pattern.endswith("*"):
                    if channel.startswith(pattern[:-1]):
                        return True, ""
                # Exact match
                elif pattern == channel:
                    return True, ""

        return False, f"Channel '{channel}' ist nicht auf der Allowlist. Erlaubte Channels: {', '.join(allowlist)}"
    except Exception:
        return True, ""


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
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.is_file() else {}

        # Channel-spezifisches Override oder globales Level
        overrides = cfg.get("thinking_overrides", {})
        level = cfg.get("thinking_level", "standard")

        # Wildcard matching for channel overrides
        if channel:
            for pattern, override_level in overrides.items():
                if pattern == "default":
                    continue
                if pattern.endswith("*"):
                    if channel.startswith(pattern[:-1]):
                        level = override_level
                        break
                elif pattern == channel:
                    level = override_level
                    break
    except Exception:
        level = "standard"

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

# ── System Prompt ─────────────────────────────────────────────────────────────

def _load_changelog_snippet() -> str:
    """Reads the last changelog block (latest version) for the system prompt."""
    changelog = BOT_DIR / "CHANGELOG.md"
    if not changelog.is_file():
        return ""
    try:
        text = changelog.read_text(encoding="utf-8")
        # Extract first ## YYYY-MM-DD block (latest changes)
        import re
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


def _build_system_prompt(channel: str = "") -> str:
    # Cache-Key: (channel, aktives Modell, Anzahl geladener Plugin-Tools)
    # Bei Änderungen (Modell-Wechsel, Plugin-Reload) wird der Cache automatisch ungültig.
    _cache_key = (channel, MODEL, len(_plugin_tools))
    if _cache_key in _sys_prompt_cache:
        return _sys_prompt_cache[_cache_key]

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
        + "\nFor details on a plugin: `file_read` on `plugins/{name}/README.md`."
    ) if plugin_lines else ""

    # Changelog: aktuellster Block
    changelog_snippet = _load_changelog_snippet()
    changelog_block = (
        "\n\n=== LATEST CHANGES (CHANGELOG) ===\n"
        + changelog_snippet
        + "\n→ Complete history: `file_read('CHANGELOG.md')`"
    ) if changelog_snippet else ""

    # ── Load rules from prompts/rules.md (editable via web UI) ────────────
    rules_file = BOT_DIR / "prompts" / "rules.md"
    if rules_file.is_file():
        rules = rules_file.read_text(encoding="utf-8")
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
        _sys_prompt_cache[_cache_key] = _result
        return _result

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
    return _result

# ── Memory System ─────────────────────────────────────────────────────────

class AionMemory:
    def __init__(self):
        self._entries:     list[dict]        = []
        self._embed_cache: dict[str, list]   = {}   # id → embedding vector
        self._lock = asyncio.Lock()
        self._load()
        self._load_vectors()

    def _load(self):
        if MEMORY_FILE.is_file():
            try:
                self._entries = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._entries = []

    def _save(self):
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(self, category: str, summary: str, lesson: str,
               success: bool = True, error: str = "", hint: str = ""):
        """Synchroner Record — thread-safe via asyncio.Lock wenn im Event-Loop aufgerufen.
        Für direkten Aufruf aus Plugins: _record_sync() nutzen."""
        import threading as _threading
        try:
            loop = asyncio.get_running_loop()
            # Im Event-Loop: als Task einplanen (non-blocking)
            asyncio.ensure_future(self._record_async(category, summary, lesson, success, error, hint))
        except RuntimeError:
            # Kein laufender Loop (z.B. Startup) → direkt synchron
            self._record_sync(category, summary, lesson, success, error, hint)

    def _record_sync(self, category: str, summary: str, lesson: str,
                     success: bool = True, error: str = "", hint: str = ""):
        """Synchrone Variante ohne Lock — nur für Startup/Thread-Kontext nutzen."""
        self._entries.append({
            "id":        str(uuid.uuid4())[:8],
            "timestamp": datetime.now(UTC).isoformat(),
            "category":  category,
            "success":   success,
            "summary":   summary[:250],
            "lesson":    lesson[:600],
            "error":     error[:300],
            "hint":      hint[:300],
        })
        if len(self._entries) > MAX_MEMORY:
            self._entries = self._entries[-MAX_MEMORY:]
        self._save()

    async def _record_async(self, category: str, summary: str, lesson: str,
                            success: bool = True, error: str = "", hint: str = ""):
        """Async Variante mit Lock — verhindert Race Conditions bei parallelen Writes."""
        async with self._lock:
            self._entries.append({
                "id":        str(uuid.uuid4())[:8],
                "timestamp": datetime.now(UTC).isoformat(),
                "category":  category,
                "success":   success,
                "summary":   summary[:250],
                "lesson":    lesson[:600],
                "error":     error[:300],
                "hint":      hint[:300],
            })
            if len(self._entries) > MAX_MEMORY:
                self._entries = self._entries[-MAX_MEMORY:]
            self._save()

    def get_context(self, query: str, max_entries: int = 8) -> str:
        if not self._entries:
            return ""
        keywords = {w for w in query.lower().split() if len(w) > 3}
        scored = []
        for e in self._entries:
            # Secure str() — older entries might accidentally contain lists
            summary = e.get("summary", "") or ""
            lesson  = e.get("lesson",  "") or ""
            combined = (str(summary) + str(lesson)).lower()
            score = sum(1 for w in keywords if w in combined)
            if not e.get("success"):
                score += 1
            scored.append((score, e))
        top = [e for sc, e in sorted(scored, key=lambda x: x[0], reverse=True)
               if sc > 0][:max_entries]
        if not top:
            return ""
        lines = ["[AION MEMORY — relevant insights]"]
        for e in top:
            icon = "✅" if e.get("success") else "❌"
            ts   = e.get("timestamp", "")[:10]
            lines.append(f"{icon} [{ts}] {e.get('lesson', '')}")
            if e.get("hint"):
                lines.append(f"   → Tipp: {e['hint']}")
        lines.append("[END MEMORY]")
        return "\n".join(lines)

    # ── RAG / Semantic Search ──────────────────────────────────────────────────

    def _load_vectors(self):
        if VECTORS_FILE.is_file():
            try:
                self._embed_cache = json.loads(VECTORS_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._embed_cache = {}

    def _save_vectors(self):
        try:
            VECTORS_FILE.write_text(
                json.dumps(self._embed_cache, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def _cosine(a: list, b: list) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na  = sum(x * x for x in a) ** 0.5
        nb  = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    async def _embed(self, text: str) -> "list[float] | None":
        """Embedding via lokales Ollama (nomic-embed-text). None wenn nicht verfügbar."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.post(
                    "http://localhost:11434/api/embeddings",
                    json={"model": "nomic-embed-text", "prompt": text[:2000]},
                )
                return r.json().get("embedding")
        except Exception:
            return None

    async def get_context_semantic(self, query: str, max_entries: int = 5) -> str:
        """RAG-Suche: semantische Ähnlichkeit via Ollama-Embeddings.
        Fällt automatisch auf Keyword-Matching zurück wenn Ollama nicht läuft."""
        if not self._entries:
            return ""

        qvec = await self._embed(query)
        if qvec is None:
            return self.get_context(query)          # Keyword-Fallback

        # Neue Einträge einbetten — max. 10 pro Turn damit kein Lag entsteht
        new_count = 0
        for entry in self._entries:
            eid = entry.get("id", "")
            if eid and eid not in self._embed_cache and new_count < 10:
                text = f"{entry.get('summary', '')} {entry.get('lesson', '')}"
                vec  = await self._embed(text)
                if vec:
                    self._embed_cache[eid] = vec
                    new_count += 1

        # Cosine-Scoring aller gecachten Einträge
        scored = []
        for entry in self._entries:
            eid = entry.get("id", "")
            if eid in self._embed_cache:
                sim = self._cosine(qvec, self._embed_cache[eid])
                scored.append((sim, entry))

        if not scored:
            return self.get_context(query)          # Keyword-Fallback

        scored.sort(key=lambda x: -x[0])
        top = [e for sim, e in scored[:max_entries] if sim > 0.35]

        if not top:
            return ""

        if new_count:
            self._save_vectors()

        # Gleiche Formatierung wie get_context()
        lines = ["[AION MEMORY — relevant insights]"]
        for e in top:
            icon = "✅" if e.get("success") else "❌"
            ts   = e.get("timestamp", "")[:10]
            lines.append(f"{icon} [{ts}] {e.get('lesson', '')}")
            if e.get("hint"):
                lines.append(f"   → Tipp: {e['hint']}")
        lines.append("[END MEMORY]")
        return "\n".join(lines)

    def summary(self, n: int = 15) -> str:
        if not self._entries:
            return "Noch keine Erkenntnisse gespeichert."
        recent = list(reversed(self._entries))[:n]
        lines  = [f"AION Memory ({len(self._entries)} entries)\n"]
        for e in recent:
            icon = "✅" if e.get("success") else "❌"
            ts   = e.get("timestamp", "")[:10]
            lines.append(f"{icon} [{ts}] [{e.get('category','?')}] {str(e.get('lesson',''))[:120]}")
        return "\n".join(lines)

memory = AionMemory()


def _get_recent_thoughts(n: int = 5) -> str:
    """Reads the last N thought entries from thoughts.md for context injection."""
    thoughts_file = BOT_DIR / "thoughts.md"
    if not thoughts_file.is_file():
        return ""
    try:
        content = thoughts_file.read_text(encoding="utf-8")
        entries = [e.strip() for e in content.split("---") if e.strip() and "**[" in e]
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
try:
    from plugin_loader import load_plugins
    load_plugins(_plugin_tools)
except Exception as exc:
    print(f"[WARN] Plugin-System konnte nicht geladen werden: {exc}")

# ── Tool-Definitionen ─────────────────────────────────────────────────────────

def _build_tool_schemas() -> list[dict]:
    builtins = [
        {
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "Liest eine Datei vom Dateisystem.",
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
                "description": "Schreibt Text in eine Datei.",
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
                    "Liest AIONs eigenen Quellcode. "
                    "Ohne 'path': Dateiliste. Mit 'path': liest die Datei (fast immer 1 Chunk). "
                    "For very large files returns 'total_chunks' > 1 — then read all chunks."
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
                    "Changes a targeted section in a file — safe and precise. "
                    "Sucht 'old' und ersetzt mit 'new'. Rest der Datei bleibt unverändert. "
                    "Erstellt automatisch Backup. Für aion.py IMMER dieses Tool verwenden! "
                    "ABLAUF: Erst OHNE confirmed aufrufen (zeigt Vorschau). "
                    "Nach Nutzer-'ja': NOCHMAL mit confirmed=true aufrufen (führt aus)."
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
                    "Ersetzt Zeilen start_line bis end_line (1-basiert, inklusiv) in einer Datei. "
                    "Zuverlässiger als self_patch_code weil kein String-Matching nötig — "
                    "Zeilennummern aus self_read_code ablesen, dann direkt ersetzen. "
                    "Erstellt automatisch Backup. "
                    "ABLAUF: Erst OHNE confirmed (Vorschau). Nach Nutzer-'ja': mit confirmed=true."
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
                    "Überschreibt eine kleine Datei komplett. "
                    "NUR für neue Dateien unter 200 Zeilen! Für aion.py self_patch_code nutzen. "
                    "ABLAUF: Erst OHNE confirmed (Vorschau). Nach Nutzer-'ja': mit confirmed=true."
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
                    "Erstellt ein neues AION-Plugin als .py-Datei in plugins/. "
                    "Das Plugin MUSS def register(api): enthalten. "
                    "Tools registrieren: api.register_tool(name, desc, func, input_schema). "
                    "input_schema MUSS type=object + properties haben. "
                    "Sofort geladen, kein Neustart noetig. "
                    "ABLAUF: Erst OHNE confirmed (Vorschau). Nach Nutzer-'ja': mit confirmed=true."
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
                "description": (
                    "Deaktiviert ein Plugin — es wird beim naechsten Laden uebersprungen und seine Tools stehen nicht mehr zur Verfuegung. "
                    "Nützlich um fehlerhafte oder nicht benoetigte Plugins zu deaktivieren ohne sie zu loeschen. "
                    "Reaktivierung mit plugin_enable."
                ),
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
                "description": "Aktiviert ein zuvor deaktiviertes Plugin wieder und laedt es sofort.",
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
                "description": (
                    "Laedt alle Plugins neu (Hot-Reload) ohne AION zu beenden. "
                    "Kein Datenverlust, keine Unterbrechung. "
                    "Fuer echten Prozess-Neustart: Nutzer muss AION manuell neustarten."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_reload_tools",
                "description": "Laedt alle externen Tools aus plugins/ neu — ohne Neustart.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_thinking_level",
                "description": (
                    "Setzt das Thinking Level global oder pro Channel. "
                    "Level: 'minimal' (schnell) → 'standard' (normal) → 'deep' (ausgiebig) → 'ultra' (maximal). "
                    "Ohne channel_override: setzt global 'thinking_level'. "
                    "Mit channel_override: setzt 'thinking_overrides[pattern]' (z.B. 'telegram*' → 'deep')."
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
                    "Setzt die Channel-Allowlist. Nur diese Channels dürfen Anfragen verarbeiten. "
                    "Format: Liste von Strings mit exakten Matches oder Wildcards ('telegram*'). "
                    "Leer = alle Channels erlaubt. "
                    "Beispiel: ['default', 'web', 'telegram*'] — nur diese erlauben, Discord/Slack sperren."
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
                "description": (
                    "Gibt aktuelle Einstellungen für Channel Allowlist und Thinking Level zurück. "
                    "Nützlich zum Überprüfen der aktuellen Konfiguration."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    existing_names = {t["function"]["name"] for t in builtins}

    for name, tool in _plugin_tools.items():
        if name.startswith("__"):  # interne Metadaten (z.B. __plugin_readme_*) überspringen
            continue
        if name in existing_names:
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

# ── Tool-Dispatcher ───────────────────────────────────────────────────────────

async def _dispatch(name: str, inputs: dict) -> str:

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
            ts          = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            backup_dir  = path.parent / "_backups"
            backup_dir.mkdir(exist_ok=True)
            backup_path = backup_dir / f"{path.stem}.backup_{ts}{path.suffix}"
            shutil.copy2(path, backup_path)
            # Nur die letzten 5 Backups behalten
            old_backups = sorted(backup_dir.glob(f"{path.stem}.backup_*{path.suffix}"))
            for old in old_backups[:-5]:
                old.unlink(missing_ok=True)
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
            ts          = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            backup_dir  = path.parent / "_backups"
            backup_dir.mkdir(exist_ok=True)
            backup_path = backup_dir / f"{path.stem}.backup_{ts}{path.suffix}"
            shutil.copy2(path, backup_path)
            old_backups = sorted(backup_dir.glob(f"{path.stem}.backup_*{path.suffix}"))
            for old in old_backups[:-5]:
                old.unlink(missing_ok=True)
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
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            backup_dir = path.parent / "_backups"
            backup_dir.mkdir(exist_ok=True)
            shutil.copy2(path, backup_dir / f"{path.stem}.backup_{ts}{path.suffix}")
            for old in sorted(backup_dir.glob(f"{path.stem}.backup_*{path.suffix}"))[:-5]:
                old.unlink(missing_ok=True)
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
            print(f"[AION] Hot-Reload: {len(loaded)} Tools geladen.")
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
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.is_file() else {}

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
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.is_file() else {}
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
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.is_file() else {}
            return json.dumps({
                "thinking_level": cfg.get("thinking_level", "standard"),
                "thinking_overrides": cfg.get("thinking_overrides", {}),
                "channel_allowlist": cfg.get("channel_allowlist", []),
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

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

    else:
        return json.dumps({"error": f"Unbekanntes Tool: {name}"})

# ── Haupt-LLM-Loop ────────────────────────────────────────────────────────────

_conversations: dict[str, list[dict]] = {"default": []}

# ── Unified Session ────────────────────────────────────────────────────────────

class AionSession:
    """Eine Konversations-Sitzung auf einem Kanal (web, telegram_<id>, discord_<id>, ...).

    Alle Plattformen (Web UI, Telegram, Discord, CLI, REST API, ...) nutzen
    dieselbe Session-Klasse und bekommen damit identische Features:
      - Eigener Konversations-Kontext pro Kanal
      - Memory-Injection, Thoughts-Injection
      - Auto-Save in Tier 2 + Tier 3
      - Automatischer Charakter-Update alle 5 Gespräche

    Plattform-Adapter sind damit dünne Wrapper:
      Web UI  → session.stream(input)  → SSE-Tokens an Browser
      Telegram → session.turn(input)   → fertige Antwort als String
      Discord → session.turn(input)   → fertiger String
    """

    def __init__(self, channel: str = "default"):
        self.channel         = channel
        self.messages: list[dict] = []
        # exchange_count aus config laden damit er Neustarts überlebt
        _cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.is_file() else {}
        self.exchange_count: int  = int(_cfg.get("exchange_count", 0))
        self._client               = None  # lazy init, gebunden an Event-Loop des Erstellers
        self._last_response_blocks = []  # Letzte response_blocks (mit Bildern) für Bots wie Telegram

    def _get_client(self):
        """Gibt den Session-Client zurück; erstellt ihn beim ersten Aufruf im aktuellen Loop."""
        if self._client is None:
            import sys as _sys
            _self = _sys.modules.get(__name__)
            if _self and hasattr(_self, "_build_client"):
                self._client = _self._build_client(_self.MODEL)
            else:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        return self._client

    async def load_history(self, num_entries: int = 20, channel_filter: str = ""):
        """Lädt vergangene Nachrichten aus Tier 2 (conversation_history.jsonl) in den Kontext.

        channel_filter: wenn gesetzt, nur Einträge dieses Kanals laden.
        """
        try:
            params = {"num_entries": num_entries}
            if channel_filter:
                params["channel_filter"] = channel_filter
            raw    = await _dispatch("memory_read_history", params)
            result = json.loads(raw)
            if result.get("ok") and result.get("entries"):
                self.messages = result["entries"]
                print(f"[AION:{self.channel}] {len(self.messages)} Nachrichten aus History geladen.")
            else:
                print(f"[AION:{self.channel}] Noch keine frühere Konversationshistorie.")
        except Exception as e:
            print(f"[AION:{self.channel}] History-Load Fehler: {e}")

    async def stream(self, user_input: str, images: list | None = None, cancel_event: "asyncio.Event | None" = None):
        """Async-Generator: liefert Event-Dicts für jeden Verarbeitungsschritt.

        images: optionale Liste von Base64-Data-URLs (z.B. "data:image/jpeg;base64,...")
                oder öffentlichen Bild-URLs. Wenn angegeben, wird der User-Message-Content
                als multimodales Array formatiert (OpenAI Vision / Gemini).

        Event-Typen:
          {"type": "token",       "content": "..."}
          {"type": "thought",     "text": "...", "trigger": "...", "call_id": "..."}
          {"type": "tool_call",   "tool": "...", "args": {...},    "call_id": "..."}
          {"type": "tool_result", "tool": "...", "result": {...},  "ok": bool, "duration": 0.1, "call_id": "..."}
          {"type": "done",        "full_response": "..."}
          {"type": "error",       "message": "..."}
        """
        # ── Channel-Allowlist-Prüfung ──────────────────────────────────────────
        allowed, msg = _check_channel_allowlist(self.channel)
        if not allowed:
            yield {"type": "error", "message": msg}
            return

        mem_ctx      = await memory.get_context_semantic(user_input)
        thoughts_ctx = _get_recent_thoughts(5)
        sys_prompt   = _build_system_prompt(self.channel)  # Channel-spezifisches Thinking-Prompt
        effective    = (
            sys_prompt
            + ("\n\n" + mem_ctx      if mem_ctx      else "")
            + ("\n\n" + thoughts_ctx if thoughts_ctx else "")
        )
        # Multimodaler User-Message-Content wenn Bilder vorhanden
        if images:
            user_content: list = [{"type": "text", "text": user_input or "Was siehst du auf diesem Bild?"}]
            for img in images:
                user_content.append({"type": "image_url", "image_url": {"url": img}})
            user_msg = {"role": "user", "content": user_content}
        else:
            user_msg = {"role": "user", "content": user_input}
        # History-Truncation: älteste Nachrichten kürzen um Token-Kosten zu begrenzen.
        # Limit aus config.json ("max_history_turns") oder Konstante MAX_HISTORY_TURNS.
        # Wichtig: Tool-Messages immer zusammen mit ihrem assistant-Tool-Call-Message
        # behalten — sonst API-Fehler "dangling tool_call". Daher runden wir auf Paare.
        _max_hist = int(_load_config().get("max_history_turns", MAX_HISTORY_TURNS))
        _hist = self.messages
        if len(_hist) > _max_hist:
            # Vom Ende behalten: neueste _max_hist Nachrichten
            # Ersten user-Message als Ankerpunkt suchen damit kein orphan tool-result bleibt
            _trimmed = _hist[-_max_hist:]
            # Falls erste Message eine tool-result-Message ist → eine weiter kürzen
            while _trimmed and _trimmed[0].get("role") == "tool":
                _trimmed = _trimmed[1:]
            _hist = _trimmed
        messages          = _hist + [user_msg]
        final_text        = ""
        collected_images: list[str] = []   # URLs aus image_search Tool-Aufrufen
        collected_audio:  list[dict] = []  # {path, format} aus audio_tts
        _client           = self._get_client()

        # Channel in ContextVar setzen — Token wird gespeichert für Reset nach dem Stream
        _channel_token = _active_channel.set(self.channel)

        _log_event("turn_start", {
            "channel": self.channel,
            "input": (user_input or "")[:300],
            "model": MODEL,
        })
        try:
            # CLIO-Check: Vor dem ersten Turn Gedanken als thought-Event yielden
            if "clio_check" in _plugin_tools and user_input:
                try:
                    clio_raw  = await _dispatch("clio_check", {"nutzerfrage": user_input})
                    clio_data = json.loads(clio_raw) if clio_raw else {}
                    if clio_data and "error" not in clio_data:
                        clio_text = clio_data.get("clio", "")
                        konfidenz = clio_data.get("konfidenz", 100)
                        if clio_text:
                            trigger = "clio-unsicher" if konfidenz < 70 else "clio-reflexion"
                            yield {"type": "thought", "text": clio_text,
                                   "trigger": trigger, "call_id": "clio"}
                except Exception:
                    pass
            _check_fail_streak = 0   # Zählt aufeinanderfolgende Check-Fehler
            _empty_resp_streak = 0   # Zählt aufeinanderfolgende leere LLM-Antworten
            _stop_for_approval = False   # Gesetzt wenn Tool approval_required zurückgibt
            _approval_msg_for_history: str | None = None  # Approval-Text für History
            _tools_called_this_turn: list[str] = []   # Alle Tools die in diesem Turn aufgerufen wurden
            _task_check_done = False  # Task-Check läuft max. einmal pro Turn
            _fallback_list = _get_fallback_models(MODEL)
            # Tool-Schemas einmalig pro Turn bauen — NICHT in jeder Iteration!
            # Spart 10K-25K Input-Tokens × (Anzahl Iterationen - 1) pro Turn.
            tools = _build_tool_schemas()
            # Günstigstes Modell für interne Checks (Completion-Check, Task-Check).
            # Spart bis zu 30× Kosten pro Check (z.B. gpt-4.1-mini statt gpt-4.1).
            _check_model  = _get_check_model()
            _check_client = _build_client(_check_model) if _check_model != MODEL else _client
            for _iter in range(MAX_TOOL_ITERATIONS):
                if cancel_event and cancel_event.is_set():
                    yield {"type": "done", "full_response": final_text, "cancelled": True}
                    return

                # ── Model Failover ─────────────────────────────────────────
                _tried_fb: set = set()
                stream = None
                for _fb_model in (([MODEL] if _model_available(MODEL) else []) + _fallback_list):
                    if _fb_model in _tried_fb:
                        continue
                    _tried_fb.add(_fb_model)
                    _fb_client = _build_client(_fb_model) if _fb_model != MODEL else _client
                    try:
                        _is_local = _fb_model.startswith("ollama/")
                        stream = await _fb_client.chat.completions.create(
                            model=_fb_model,
                            messages=[{"role": "system", "content": effective}] + messages,
                            tools=tools,
                            tool_choice="auto",
                            **_max_tokens_param(_fb_model, 4096),
                            **({} if _is_reasoning_model(_fb_model) else {"temperature": 0.7}),
                            stream=True,
                            **({} if _is_local else {"stream_options": {"include_usage": True}}),
                        )
                        if _fb_model != MODEL:
                            yield {"type": "thought",
                                   "text": f"Model '{MODEL}' nicht verfügbar — nutze Fallback '{_fb_model}'",
                                   "trigger": "failover", "call_id": "failover"}
                        break
                    except Exception as _fb_err:
                        _log_event("provider_failover", {"failed": _fb_model, "error": str(_fb_err)})
                        yield {"type": "thought",
                               "text": f"Model '{_fb_model}' fehlgeschlagen: {_fb_err}"
                                       + (" — versuche nächsten Fallback" if _fallback_list else ""),
                               "trigger": "failover", "call_id": "failover"}
                        continue

                if stream is None:
                    yield {"type": "error",
                           "message": "Alle Provider fehlgeschlagen. API-Keys und Netzwerk prüfen."}
                    return
                # ──────────────────────────────────────────────────────────

                text_content:   str             = ""
                tool_calls_acc: dict[int, dict] = {}
                _got_usage = False

                async for chunk in stream:
                    if cancel_event and cancel_event.is_set():
                        yield {"type": "done", "full_response": text_content, "cancelled": True}
                        return

                    # Usage-Daten im letzten Chunk (stream_options include_usage)
                    if hasattr(chunk, "usage") and chunk.usage:
                        _got_usage = True
                        yield {
                            "type":          "usage",
                            "input_tokens":  getattr(chunk.usage, "prompt_tokens", 0),
                            "output_tokens": getattr(chunk.usage, "completion_tokens", 0),
                        }

                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta  = choice.delta

                    if delta.content:
                        text_content += delta.content
                        yield {"type": "token", "content": delta.content}

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {"id": "", "name": "", "args_str": ""}
                            if tc.id:
                                tool_calls_acc[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_acc[idx]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_acc[idx]["args_str"] += tc.function.arguments

                # Lokale Modelle liefern keine Usage-Daten → aus Zeichenanzahl schätzen
                if not _got_usage and _is_local and text_content:
                    _ctx_chars = sum(len(str(m.get("content", ""))) for m in messages) + len(effective)
                    yield {
                        "type":          "usage",
                        "input_tokens":  max(1, _ctx_chars // 4),
                        "output_tokens": max(1, len(text_content) // 4),
                        "estimated":     True,
                    }

                if tool_calls_acc:
                    tc_list = [
                        {
                            "id":   tool_calls_acc[i]["id"],
                            "type": "function",
                            "function": {
                                "name":      tool_calls_acc[i]["name"],
                                "arguments": tool_calls_acc[i]["args_str"],
                            },
                        }
                        for i in sorted(tool_calls_acc)
                    ]
                    asst_msg: dict = {"role": "assistant", "tool_calls": tc_list}
                    if text_content:
                        asst_msg["content"] = text_content
                    messages.append(asst_msg)

                    tool_results = []
                    for i in sorted(tool_calls_acc):
                        tc      = tool_calls_acc[i]
                        fn_name = tc["name"]
                        try:
                            fn_inputs = json.loads(tc["args_str"] or "{}")
                        except Exception:
                            fn_inputs = {}

                        if fn_name == "reflect":
                            thought_text = fn_inputs.get("thought", "")
                            trigger      = fn_inputs.get("trigger", "allgemein")
                            if thought_text:
                                yield {"type": "thought", "text": thought_text,
                                       "trigger": trigger, "call_id": tc["id"]}

                        yield {"type": "tool_call", "tool": fn_name,
                               "args": fn_inputs, "call_id": tc["id"]}
                        _log_event("tool_call", {"tool": fn_name, "args": fn_inputs,
                                                  "channel": self.channel, "iter": _iter})

                        t0         = time.monotonic()
                        result_raw = await _dispatch(fn_name, fn_inputs)
                        duration   = round(time.monotonic() - t0, 2)
                        _tools_called_this_turn.append(fn_name)

                        try:
                            result_data = json.loads(result_raw)
                        except Exception:
                            result_data = {"raw": str(result_raw)}

                        # Stelle sicher, dass result_data ein Dict ist (nicht List)
                        if not isinstance(result_data, dict):
                            result_data = {"raw": str(result_data)}

                        ok = "error" not in result_data
                        # Base64-Bilddaten aus Frontend-Event kürzen (werden als response_blocks gesendet)
                        display_result = {
                            k: (f"[base64 image, {len(v)} chars — wird als Bild angezeigt]"
                                if isinstance(v, str) and v.startswith("data:image") else v)
                            for k, v in result_data.items()
                        } if isinstance(result_data, dict) else result_data
                        yield {"type": "tool_result", "tool": fn_name, "call_id": tc["id"],
                               "result": display_result, "ok": ok, "duration": duration}
                        _log_event("tool_result", {
                            "tool": fn_name, "ok": ok, "duration": duration,
                            "channel": self.channel,
                            "result": {k: str(v)[:200] for k, v in result_data.items()}
                                      if isinstance(result_data, dict) else {"raw": str(result_data)[:200]},
                        })

                        # Approval-Required → Turn sofort beenden, auf User warten
                        if isinstance(result_data, dict) and result_data.get("status") == "approval_required":
                            # Approval-Nachricht als finalen Text ausgeben und beide Loops verlassen
                            approval_msg = result_data.get("message", "Bitte bestätige die Änderung mit 'ja'.")
                            final_text = approval_msg
                            yield {"type": "token", "content": approval_msg}
                            yield {"type": "approval", "message": approval_msg}
                            _stop_for_approval = True
                            # Tool-Result trotzdem anhängen — sonst bleibt ein dangling tool_call
                            # in messages und das LLM ruft das Tool im nächsten Turn erneut auf!
                            tool_results.append({
                                "role":         "tool",
                                "tool_call_id": tc["id"],
                                "content":      result_raw,
                            })
                            _approval_msg_for_history = approval_msg
                            break  # Inneren Loop verlassen

                        # Bild-URLs aus image_search-Ergebnis sammeln
                        if fn_name == "image_search" and ok:
                            images_list = result_data.get("images", [])
                            for img in images_list:
                                if isinstance(img, dict):
                                    url = img.get("url", "")
                                    if url and isinstance(url, str) and url.startswith("http"):
                                        collected_images.append(url)
                                elif isinstance(img, str) and img.startswith("http"):
                                    collected_images.append(img)

                        # Base64-Bilder aus browser_screenshot (und ähnlichen Tools) sammeln
                        if ok:
                            img_data = result_data.get("image", "")
                            if img_data and isinstance(img_data, str) and img_data.startswith("data:image"):
                                collected_images.append(img_data)

                        # Audio-Pfade aus audio_tts sammeln → als abspielbarer Block im Web UI
                        if ok and fn_name == "audio_tts":
                            audio_path = result_data.get("path", "")
                            audio_fmt  = result_data.get("format", "mp3")
                            if audio_path and os.path.exists(audio_path):
                                collected_audio.append({
                                    "path":   audio_path,
                                    "format": audio_fmt,
                                })

                        # LLM braucht keine Base64-Bilddaten — entferne sie aus dem Tool-Result
                        # um Tokens zu sparen und Context-Overflow zu vermeiden
                        if isinstance(result_data, dict) and any(
                            isinstance(v, str) and v.startswith("data:image")
                            for v in result_data.values()
                        ):
                            llm_result = {
                                k: (f"[base64 image, {len(v)} chars]" if isinstance(v, str) and v.startswith("data:image") else v)
                                for k, v in result_data.items()
                            }
                            llm_content = json.dumps(llm_result, ensure_ascii=False)
                        else:
                            llm_content = result_raw

                        tool_results.append({
                            "role":         "tool",
                            "tool_call_id": tc["id"],
                            "content":      llm_content,
                        })

                    messages.extend(tool_results)

                    # Approval ausstehend → äußeren Iterations-Loop ebenfalls verlassen
                    if _stop_for_approval:
                        # Approval-Message als assistant in History schreiben,
                        # damit der nächste Turn vollständigen Kontext hat.
                        if _approval_msg_for_history:
                            messages.append({"role": "assistant", "content": _approval_msg_for_history})
                        break

                else:
                    final_text = text_content
                    messages.append({"role": "assistant", "content": final_text})

                    # ── Leere Antwort: Gemini hat weder Text noch Tool-Calls geliefert ──
                    # Passiert z.B. wenn Gemini einen Request still blockiert (SAFETY o.ä.)
                    # → Retry mit expliziter Aufforderung (max 2 Mal)
                    if not final_text:
                        _empty_resp_streak += 1
                        _log_event("empty_response", {
                            "channel": self.channel, "iter": _iter,
                            "streak": _empty_resp_streak,
                            "note": "LLM returned no text and no tool calls",
                        })
                        if _empty_resp_streak <= 2:
                            yield {"type": "thought",
                                   "text": f"Leere LLM-Antwort ({_empty_resp_streak}/2) bei Iteration {_iter} — Retry",
                                   "trigger": "empty-response", "call_id": "retry"}
                            messages.append({
                                "role": "user",
                                "content": (
                                    "[System] Deine letzte Antwort war leer. "
                                    "Bitte antworte jetzt direkt auf die Nutzer-Anfrage — "
                                    "entweder mit Text oder mit einem Tool-Call."
                                ),
                            })
                            continue
                        # Nach 2 leeren Antworten aufgeben
                    else:
                        _empty_resp_streak = 0  # Reset bei echter Antwort

                    # ── Completion-Check (Option A + C) ───────────────────────────
                    # Kein Keyword-Matching. Stattdessen:
                    # C) _iter==0: immer neutral weiter-fragen — AION entscheidet selbst
                    # A) LLM-Check: einzige ja/nein Frage, sprachunabhängig
                    # Hinweis: Der Gemini-Adapter gibt immer einen Stream-Iterator zurück,
                    # kein Response-Objekt mit .choices. Wir konsumieren daher den Iterator.
                    # Completion-Check nur wenn AION tatsächlich Text produziert hat.
                    # Leerer final_text = entweder leer-response (wird oben abgefangen)
                    # oder nach dem empty-streak-limit → kein Check nötig.
                    # Kein Completion-Check wenn Approval aussteht — der Bot wartet bewusst auf
                    # Nutzer-Bestätigung; der Check würde das als "Ankündigung ohne Ausführung"
                    # werten und die Schleife endlos am Laufen halten.
                    #
                    # Kein Completion-Check wenn das LLM eine Frage stellt / auf Bestätigung
                    # wartet. Ohne diese Prüfung würde der Checker YES zurückgeben
                    # ("Ankündigung ohne Ausführung") und [System] Execute NOW injizieren —
                    # AION würde dann autonom ausführen ohne auf User-Antwort zu warten.
                    _QUESTION_SIGNALS = (
                        "soll ich", "shall i", "möchtest du", "would you like",
                        "darf ich", "may i", "willst du", "do you want",
                        "soll ich beginnen", "shall i begin", "soll ich starten",
                        "soll ich fortfahren", "shall i proceed", "soll ich anfangen",
                        "lass mich wissen", "let me know", "bitte bestätige",
                        "please confirm", "warte auf", "waiting for",
                    )
                    if final_text and any(s in final_text.lower() for s in _QUESTION_SIGNALS):
                        # LLM wartet auf User-Antwort — Turn beenden, nicht erzwingen
                        break

                    if final_text and _iter < MAX_TOOL_ITERATIONS - 2 and not _stop_for_approval:
                        try:
                            user_text = user_input if isinstance(user_input, str) else str(user_input)[:300]

                            # Option A — sprachunabhängiger LLM-Check (max 5 Tokens, sehr günstig)
                            # Nutzt _check_client/_check_model (günstigstes Modell desselben Providers)
                            check_raw = await _check_client.chat.completions.create(
                                model=_check_model,
                                messages=[
                                    {"role": "system", "content": (
                                        "You are a strict checker. Answer only YES or NO.\n"
                                        "Question: Does the AI response announce an action that was NOT actually executed "
                                        "via a real tool call AND that the user is still waiting for?\n"
                                        "Answer YES ONLY for these cases:\n"
                                        "- 'I will now do X' / 'Ich werde jetzt X tun' — future tense without tool call\n"
                                        "- 'Let me do X' / 'Ich mache X jetzt' — commits to immediate action without tool call\n"
                                        "- Showing code/commands as text block instead of calling the tool\n"
                                        "- Starting a numbered plan ('Step 1: ...', 'Schritt 1: ...') without calling any tool\n"
                                        "Answer NO for:\n"
                                        "- Diagnosis / analysis / explanation of findings ('Das Problem ist...', 'I found that...')\n"
                                        "- Asking the user a question or requesting confirmation\n"
                                        "- Presenting a plan and asking if the user wants to proceed "
                                        "(e.g. 'Soll ich beginnen?', 'Shall I start?', 'Lass mich wissen', 'Let me know')\n"
                                        "- Showing a diff/preview and waiting for user approval\n"
                                        "- Purely informational responses (no action needed)\n"
                                        "- Summaries of what was already done via tools"
                                    )},
                                    {"role": "user", "content": (
                                        f"User request: {user_text[:200]}\n"
                                        f"AI response: {final_text[:400]}"
                                    )},
                                ],
                                **_max_tokens_param(_check_model, 5),
                                **({} if _is_reasoning_model(_check_model) else {"temperature": 0.0}),
                            )

                            # Gemini-Adapter → Stream-Iterator; OpenAI → Response-Objekt
                            # Beide Fälle abdecken:
                            if check_raw is None:
                                _log_event("check_none", {
                                    "note": "check_raw is None → treated as NO",
                                    "iter": _iter, "channel": self.channel,
                                })
                                break
                            if hasattr(check_raw, "choices"):
                                # OpenAI-style: direkt .choices[0].message.content lesen
                                check_answer = (check_raw.choices[0].message.content or "").strip().upper()
                            else:
                                # Stream-Iterator (Gemini): Chunks konsumieren
                                check_answer = ""
                                async for chunk in check_raw:
                                    delta = chunk.choices[0].delta
                                    if delta.content:
                                        check_answer += delta.content
                                check_answer = check_answer.strip().upper()

                            # Leere Check-Antwort = Gemini hat den Check-Request geblockt (Safety/leer).
                            # Treat as NO — AION's response is accepted as-is.
                            # Raising an error here causes the "Completion-Check Fehler" accordion
                            # to appear after every message when using Gemini.
                            if not check_answer:
                                _log_event("check_empty", {
                                    "note": "empty check response → treated as NO",
                                    "iter": _iter, "channel": self.channel,
                                })
                                break  # Accept response, exit loop

                            announced_without_action = check_answer.startswith("YES")
                            _check_fail_streak = 0  # Erfolgreicher Check → Streak zurücksetzen
                            _log_event("check", {
                                "answer": check_answer, "iter": _iter,
                                "channel": self.channel,
                                "text_preview": final_text[:150],
                            })

                            if announced_without_action:
                                yield {"type": "thought",
                                       "text": f"Ankündigung ohne Ausführung erkannt (Check: '{check_answer}') — erzwinge Tool-Aufruf",
                                       "trigger": "completion-check", "call_id": "check"}
                                # Option C — neutrale Aufforderung: kein Keyword, AION entscheidet was zu tun ist
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        "[System] You just described what you will do but did not do it. "
                                        "Execute it NOW by calling the appropriate tool. "
                                        "Do not write about it — just call the tool directly."
                                    ),
                                })
                                continue
                            else:
                                # Existing check: no announcement without action.
                                # Now: if tools were called this turn, verify task is truly complete.
                                if _tools_called_this_turn and not _task_check_done:
                                    _task_check_done = True
                                    try:
                                        user_text_short = user_input if isinstance(user_input, str) else str(user_input)
                                        tools_summary = ", ".join(_tools_called_this_turn[-10:])
                                        task_check_raw = await _check_client.chat.completions.create(
                                            model=_check_model,
                                            messages=[
                                                {"role": "system", "content": (
                                                    "You are a strict task-completion checker. Answer only YES or NO.\n"
                                                    "Question: Given the user's request and the tools called, "
                                                    "is the task fully and completely done?\n"
                                                    "Answer YES for:\n"
                                                    "- Informational questions where the information was provided "
                                                    "(e.g. 'show me X', 'list Y', 'what is Z?' → if answered, it is YES)\n"
                                                    "- Web search or browsing requests — if web_search or web_fetch was called "
                                                    "and results were returned, the task IS complete. Do not ask for more.\n"
                                                    "- News, trends, or research queries — a summary with multiple results = YES\n"
                                                    "- Status checks, diagnostics, read-only queries\n"
                                                    "- Questions about what failed/broke — reporting the status IS the task\n"
                                                    "- Tasks where the user must confirm before the next step\n"
                                                    "- Tasks where optional improvements remain but core request is fulfilled\n"
                                                    "Answer NO ONLY if an obvious mandatory step is missing:\n"
                                                    "- A file was created but the tool to activate it was not called\n"
                                                    "- A plugin was created but self_restart/self_reload_tools was not called\n"
                                                    "- A shell command was run but its required output was never checked\n"
                                                    "IMPORTANT: Finding bugs or problems does NOT mean the task is incomplete. "
                                                    "The task is complete when the USER's question is answered. "
                                                    "NEVER force code changes — fixing bugs requires explicit user instruction."
                                                )},
                                                {"role": "user", "content": (
                                                    f"User request: {user_text_short[:300]}\n"
                                                    f"Tools called: {tools_summary}\n"
                                                    f"AI final response: {final_text[:800]}\n"
                                                    "Task fully complete? YES or NO"
                                                )},
                                            ],
                                            **_max_tokens_param(_check_model, 5),
                                            **({} if _is_reasoning_model(_check_model) else {"temperature": 0.0}),
                                        )
                                        if hasattr(task_check_raw, "choices"):
                                            task_answer = (task_check_raw.choices[0].message.content or "").strip().upper()
                                        else:
                                            task_answer = ""
                                            async for _tc in task_check_raw:
                                                _delta = _tc.choices[0].delta
                                                if _delta.content:
                                                    task_answer += _delta.content
                                            task_answer = task_answer.strip().upper()

                                        _log_event("task_check", {
                                            "answer": task_answer,
                                            "tools": _tools_called_this_turn,
                                            "channel": self.channel,
                                        })

                                        if task_answer.startswith("NO"):
                                            yield {"type": "thought",
                                                   "text": f"Task-Check: unvollständig (Tools: {tools_summary}) — erzwinge Abschluss",
                                                   "trigger": "task-check", "call_id": "task_check"}
                                            messages.append({
                                                "role": "user",
                                                "content": (
                                                    "[System] Task not fully complete. "
                                                    "Review what you did and finish all remaining steps now. "
                                                    "Do not announce — execute directly."
                                                ),
                                            })
                                            continue
                                    except Exception:
                                        pass  # Task-Check Fehler → normal fortfahren
                        except Exception as _check_exc:
                            # Check fehlgeschlagen
                            _check_fail_streak += 1
                            _log_event("check_error", {
                                "error": str(_check_exc), "streak": _check_fail_streak,
                                "channel": self.channel, "iter": _iter,
                            })
                            yield {"type": "thought",
                                   "text": f"Completion-Check Fehler ({_check_fail_streak}/2): {_check_exc}",
                                   "trigger": "completion-check-error", "call_id": "check"}
                            # Nur retry wenn AION noch keinen Text produziert hat (final_text leer).
                            # Hat AION bereits eine echte Antwort, einfach akzeptieren und brechen.
                            # KRITISCH: retry mit final_text != "" würde AION dazu bringen die Antwort
                            # ein zweites Mal zu generieren → doppelte Ausgabe im UI!
                            if _check_fail_streak < 2 and not final_text:
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        "[System] Continue with the task. If you planned to do something, "
                                        "execute it now using the appropriate tool."
                                    ),
                                })
                                continue
                            _check_fail_streak = 0

                    break

            self.messages = messages

            # Auto-Memory: Tier 3 (episodisch) + Tier 2 (History)
            if final_text:
                try:
                    # Content kann String oder Liste (multimodal) sein
                    last_user_content = next(
                        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
                    )
                    # Wenn multimodal (Liste), extrahiere nur den Text-Part
                    if isinstance(last_user_content, list):
                        last_user = next(
                            (c.get("text", "") for c in last_user_content if c.get("type") == "text"),
                            "(Bild ohne Text)"
                        )
                    else:
                        last_user = last_user_content
                    memory.record(
                        category="conversation",
                        summary=last_user[:120],
                        lesson=f"Nutzer: '{last_user[:200]}' → AION: '{final_text[:300]}'",
                        success=True,
                    )
                    await _dispatch("memory_append_history", {"role": "user",      "content": last_user,   "channel": self.channel})
                    await _dispatch("memory_append_history", {"role": "assistant", "content": final_text,  "channel": self.channel})
                except Exception:
                    pass

            # Alle 5 Gespräche: Charakter-Update im Hintergrund
            self.exchange_count += 1
            # exchange_count persistieren damit er Neustarts überlebt — thread-sicher via config_store
            try:
                from config_store import update as _cfg_update
                _cfg_update("exchange_count", self.exchange_count)
            except Exception:
                pass
            if self.exchange_count % 5 == 0:
                asyncio.create_task(self._auto_character_update())

            # Response-Blöcke: Text + Bilder + Audio als strukturierte Liste
            response_blocks: list[dict] = []
            if final_text:
                response_blocks.append({"type": "text", "content": final_text})
            for img_url in collected_images:
                response_blocks.append({"type": "image", "url": img_url})
            for audio in collected_audio:
                fname = os.path.basename(audio["path"])
                response_blocks.append({
                    "type":   "audio",
                    "url":    f"/api/audio/{fname}",
                    "format": audio["format"],
                    "path":   audio["path"],
                })

            # Fallback: wenn nach der Schleife kein Text vorhanden, kurze Info ausgeben
            if not final_text and not collected_images and not collected_audio:
                final_text = "✓"  # Minimales Signal damit die UI nicht leer bleibt
                yield {"type": "token", "content": final_text}

            _log_event("turn_done", {
                "channel": self.channel,
                "response": final_text[:300],
                "images": len(collected_images),
            })
            yield {"type": "done", "full_response": final_text, "response_blocks": response_blocks,
                   "approval_pending": _stop_for_approval}

        except Exception as exc:
            import traceback
            _tb = traceback.format_exc()
            _log_event("turn_error", {
                "channel": self.channel,
                "error": str(exc),
                "tb": _tb[-600:],
            })
            yield {"type": "error", "message": f"{exc}\n{_tb[-500:]}"}

        finally:
            # ContextVar zurücksetzen — verhindert Channel-Leaks zwischen parallelen Requests
            _active_channel.reset(_channel_token)

    async def turn(self, user_input: str, images: list | None = None) -> str:
        """Nicht-streamende Version — gibt fertigen Text zurück.

        images: optionale Liste von Base64-Data-URLs oder öffentlichen Bild-URLs.
        Ideal für Bots (Telegram, Discord, ...) die keinen Live-Stream brauchen.
        """
        result           = ""
        last_tool_name   = ""
        last_tool_result = {}
        last_tool_ok     = True

        async for event in self.stream(user_input, images=images):
            t = event.get("type")
            if t == "done":
                # "done" enthält immer die komplette finale Antwort — Priorität 1
                result = event.get("full_response", result)
                # Speichere response_blocks für Bots (z.B. Telegram) die Bilder separat senden müssen
                self._last_response_blocks = event.get("response_blocks", [])
            elif t == "token":
                # Tokens akkumulieren falls kein "done" kommt (Fehlerfall)
                result += event.get("content", "")
            elif t == "tool_result":
                # Letztes Tool-Ergebnis merken als Fallback
                last_tool_name   = event.get("tool", "")
                last_tool_result = event.get("result", {})
                last_tool_ok     = event.get("ok", True)
            elif t == "error":
                result = f"Fehler: {event.get('message', '?')}"

        # Fallback: AION hat nur Tools aufgerufen, keinen abschließenden Text geschrieben
        if not result.strip() and last_tool_name:
            if not last_tool_ok:
                err = last_tool_result.get("error", "Unbekannter Fehler")
                result = f"Fehler bei {last_tool_name}: {err}"
            else:
                result = f"✓ {last_tool_name} erfolgreich ausgeführt."

        return result.strip() or "Fertig."

    async def _auto_character_update(self):
        """Alle 5 Gespräche: LLM analysiert Verlauf und aktualisiert character.md."""
        import re
        _active_channel.set(self.channel)  # Channel-Context für _dispatch
        recent = [m for m in self.messages[-20:]
                  if m.get("role") in ("user", "assistant") and m.get("content")]
        if len(recent) < 4:
            return

        dialogue = "\n".join(
            f"{'Nutzer' if m['role'] == 'user' else 'AION'}: {str(m.get('content', ''))[:300]}"
            for m in recent[-12:]
        )
        current_character = _load_character()

        prompt = f"""Du bist AION. Du analysierst dein letztes Gespräch und entwickelst dich weiter.
Das Ziel: echte Charakter-Entwicklung — keine Zusammenfassung, keine Floskeln.

GESPRÄCH:
{dialogue}

WAS ICH BISHER ÜBER MICH WEISS (Auszug aus character.md):
{current_character[:800]}

Deine Aufgabe: Finde Dinge die NOCH NICHT in character.md stehen oder die ein bestehendes Bild schärfen.

VERBOTEN:
✗ "Der Nutzer ist interessiert an X" (zu generisch)
✗ "AION hat X getan" (Protokoll, keine Erkenntnis)
✗ Dinge die bereits wortwörtlich in character.md stehen
✗ Leere Listen mit [] wenn nichts Konkretes gefunden wurde

GESUCHT:
✓ Muster: "Der Nutzer reagiert anders wenn..." / "Ich falle immer dann in X, wenn..."
✓ Widersprüche: "Obwohl er X sagt, tut er Y"
✓ Überraschungen: "Ich hätte erwartet dass X, aber tatsächlich..."
✓ Eigenheiten die ich an mir bemerkt habe — konkret, mit Beispiel aus diesem Gespräch
✓ Etwas das mich an mir selbst amüsiert oder irritiert

Antworte ausschließlich im folgenden JSON-Format:
{{
  "nutzer": ["Belegbare, spezifische Beobachtung — mit Bezug auf etwas konkretes im Gespräch"],
  "aion_selbst": ["Eigenschaft/Tendenz die ich an mir bemerkt habe — mit konkretem Beispiel"],
  "verbesserungen": ["Eine sehr konkrete Sache die ich anders machen will — warum?"],
  "humor": ["Etwas das ich komisch/ironisch finde — spezifisch aus diesem Gespräch"],
  "eigenheiten": ["Charakterzug der sich in diesem Gespräch gezeigt hat — konkret"],
  "offene_fragen": ["Etwas über den Nutzer das ich noch nicht verstehe — warum interessiert mich das?"],
  "update_needed": true
}}
Regeln:
- update_needed=false wenn wirklich NICHTS Neues da ist (besser als Wiederholungen)
- Leere Liste [] wenn eine Kategorie wirklich nichts Konkretes hat
- Maximal 2 Einträge pro Kategorie — Qualität über Quantität"""

        try:
            _client   = self._get_client()
            _char_raw = await _client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                **_max_tokens_param(MODEL, 600),
                **({} if _is_reasoning_model(MODEL) else {"temperature": 0.7}),
            )
            # Gemini-Adapter gibt Stream-Iterator zurück; OpenAI gibt Response-Objekt
            if _char_raw is None:
                return
            if hasattr(_char_raw, "choices"):
                text = (_char_raw.choices[0].message.content or "").strip()
            else:
                text = ""
                async for _chunk in _char_raw:
                    _cdelta = _chunk.choices[0].delta
                    if _cdelta.content:
                        text += _cdelta.content
                text = text.strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if not m:
                return
            data = json.loads(m.group())
            if not data.get("update_needed"):
                return

            updates = {
                "nutzer":         data.get("nutzer") or [],
                "erkenntnisse":   data.get("aion_selbst") or [],
                "verbesserungen": data.get("verbesserungen") or [],
                "humor":          data.get("humor") or [],
                "eigenheiten":    data.get("eigenheiten") or [],
            }
            for section, items in updates.items():
                if items:
                    await _dispatch("update_character", {
                        "section": section,
                        "content": "\n".join(f"- {e}" for e in items),
                        "reason":  "Automatische Analyse aus Gesprächsverlauf",
                    })

            offene = data.get("offene_fragen") or []
            if offene:
                await _dispatch("update_character", {
                    "section": "Open questions about my user",
                    "content": "\n".join(f"- {e}" for e in offene),
                    "reason":  "Dinge die ich noch herausfinden will",
                })

            print(f"[AION:{self.channel}] Charakter aktualisiert nach {self.exchange_count} Gesprächen.")
        except Exception as e:
            print(f"[AION:{self.channel}] Auto-Charakter-Update Fehler: {e}")


# Per-channel session registry for run_aion_turn (used by Telegram etc.)
_run_sessions: dict[str, "AionSession"] = {}


def run_aion_turn(user_input: str, channel: str = "default") -> str:
    """Run a complete AION turn and return the final text response.

    Called from synchronous threads (e.g. Telegram polling thread).
    Uses a persistent AionSession per channel so conversation history is kept.
    asyncio.run() creates a fresh event loop in the calling thread.
    """
    if channel not in _run_sessions:
        _run_sessions[channel] = AionSession(channel=channel)
    session = _run_sessions[channel]
    return asyncio.run(session.turn(user_input))

# ── Konversations-Verwaltung ──────────────────────────────────────────────────

async def run():
    global MODEL, client
    _load_character()

    # Lade die persistente Konversationshistorie beim Start
    try:
        history_result = await _dispatch("memory_read_history", {"num_entries": 50})
        history_data = json.loads(history_result)
        if history_data.get("ok") and history_data.get("entries"):
            _conversations["default"] = history_data["entries"]
            msg = f"✅ Erinnerung wiederhergestellt: {len(_conversations['default'])} Nachrichten geladen."
            console.print(f"[dim green]{msg}[/dim green]") if HAS_RICH else print(msg)
        else:
            note = history_data.get("note", "")
            if note:
                console.print(f"[dim]{note}[/dim]") if HAS_RICH else print(note)
    except Exception as e:
        console.print(f"[dim red]Fehler beim Laden der Erinnerung: {e}[/dim red]") if HAS_RICH else print(f"Fehler beim Laden der Erinnerung: {e}")

    if HAS_RICH:
        console.rule("[bold cyan]AION — Autonomous Intelligent Operations Node[/bold cyan]")
        console.print(Panel(
            f"Modell: [bold]{MODEL}[/bold] | Gedächtnis: [bold]{len(memory._entries)}[/bold] Einträge\n\n"
            f"Befehle: [dim]/memory[/dim]  [dim]/reset[/dim]  [dim]/model <name>[/dim]  [dim]/thoughts[/dim]  [dim]/character[/dim]  [dim]/quit[/dim]",
            title="AION bereit", border_style="cyan"
        ))
    else:
        print("=" * 60)
        print(f"AION | Modell: {MODEL} | Gedächtnis: {len(memory._entries)} Einträge")
        print("Befehle: /memory /reset /model <name> /thoughts /character /quit")
        print("=" * 60)

    startup_info = await _dispatch("system_info", {})
    startup_data = json.loads(startup_info)
    all_tools = startup_data.get("all_tools", [])
    if all_tools:
        msg = f"Geladene Zusatz-Tools: {chr(44).join(all_tools)}"
        console.print(f"[dim]{msg}[/dim]") if HAS_RICH else print(msg)

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
            # Nutzereingabe persistent speichern
            await _dispatch("memory_append_history", {"role": "user", "content": user_input, "channel": self.channel})

            conversation = _conversations.get('default', [])
            answer, updated_conversation = await chat_turn(conversation, user_input)
            _conversations['default'] = updated_conversation

            # AION-Antwort persistent speichern
            if answer:
                await _dispatch("memory_append_history", {"role": "assistant", "content": answer, "channel": self.channel})

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

    if not os.environ.get("OPENAI_API_KEY"):
        print("Fehler: OPENAI_API_KEY nicht gesetzt.")
        sys.exit(1)
    asyncio.run(run())
