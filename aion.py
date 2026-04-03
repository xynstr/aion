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

from core.aion_config import (
    BOT_DIR, CONFIG_FILE, MEMORY_FILE, VECTORS_FILE, PLUGINS_DIR, TOOLS_DIR,
    CHARACTER_FILE, MAX_MEMORY, MAX_TOOL_ITERATIONS, MAX_HISTORY_TURNS,
    CHUNK_SIZE, CHARACTER_MAX_CHARS, RULES_COMPRESS_THRESHOLD,
    LOG_FILE, LOG_MAX_BYTES, UTC,
    _log_event, _load_config, save_model_config,
)

# Active channel for _dispatch — set at the beginning of stream()
_active_channel: contextvars.ContextVar[str] = contextvars.ContextVar("aion_channel", default="default")


# Model resolution: config.json → environment variable → fallback
_cfg = _load_config()
MODEL = _cfg.get("model") or os.environ.get("AION_MODEL", "gpt-4.1")

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

# ── Provider Registry ─────────────────────────────────────────────────────────

from core.aion_providers import (
    _provider_registry, register_provider,
    _resolve_ollama_prefix, _build_client, _api_model_name,
    _CHEAP_CHECK_MODELS,
)


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


from core.aion_permissions import (
    PERMISSION_DEFAULTS, PERMISSION_LABELS,
    _load_permissions, _permissions_prompt,
    _match_pattern, _check_channel_allowlist, _get_thinking_prompt,
)


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


from core.aion_character import (
    DEFAULT_CHARACTER, _load_character,
    _backup_file, _backup_code_file,
)


from core.aion_prompt import (
    _load_changelog_snippet,
    _sys_prompt_cache, invalidate_sys_prompt_cache,
    _get_mood_hint, _get_temporal_hint, _get_relationship_hint,
)


def _build_system_prompt(channel: str = "") -> str:
    # Cache-Key: (channel, aktives Modell, Anzahl geladener Plugin-Tools)
    # Bei Änderungen (Modell-Wechsel, Plugin-Reload) wird der Cache automatisch ungültig.
    _cache_key = (channel, MODEL, len(_plugin_tools))
    if _cache_key in _sys_prompt_cache:
        # Base prompt cached — append dynamic hints (mood, time, relationship, mistakes, doc-freshness, offline)
        _mistakes = _get_mistakes_hint()
        return (
            _sys_prompt_cache[_cache_key]
            + _get_mood_hint()
            + _get_temporal_hint()
            + _get_relationship_hint()
            + _get_doc_freshness_hint()
            + _get_offline_hint()
            + ("\n\n" + _mistakes if _mistakes else "")
        )

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
        # Grouped capability index — auto-generated from all registered tools (tier 1+2).
        # Gives the LLM a semantic, grouped overview so it never has to guess tool names.
        capability_block = "\n\n" + _build_capability_index()
        _result = rules + plugin_block + changelog_block + perms_block + thinking_block + capability_block
        if len(_sys_prompt_cache) > 20:
            _sys_prompt_cache.clear()
        _sys_prompt_cache[_cache_key] = _result
        _mistakes = _get_mistakes_hint()
        return (
            _result
            + _get_mood_hint()
            + _get_temporal_hint()
            + _get_relationship_hint()
            + _get_doc_freshness_hint()
            + _get_offline_hint()
            + ("\n\n" + _mistakes if _mistakes else "")
        )

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
    _mistakes = _get_mistakes_hint()
    return (
        _result
        + _get_mood_hint()
        + _get_temporal_hint()
        + _get_relationship_hint()
        + _get_doc_freshness_hint()
        + _get_offline_hint()
        + ("\n\n" + _mistakes if _mistakes else "")
    )


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
from core.aion_memory import AionMemory

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

def _get_mistakes_hint(n: int = 5) -> str:
    """Inject the last N recorded mistakes into the session context.

    Gives AION immediate awareness of past errors at the start of every session,
    creating a persistent self-improvement loop without manual maintenance.
    """
    mistakes_file = BOT_DIR / "mistakes.md"
    if not mistakes_file.is_file():
        return ""
    try:
        content = mistakes_file.read_text(encoding="utf-8")
        entries = [e.strip() for e in content.split("\n---\n") if e.strip() and "**Fehler:**" in e]
        if not entries:
            return ""
        recent = entries[-n:]
        return (
            "[AION PAST MISTAKES — learn from these, do not repeat them]\n"
            + "\n---\n".join(recent)
            + "\n[END MISTAKES]"
        )
    except Exception:
        return ""


def _get_doc_freshness_hint() -> str:
    """Warn AION if core source files are newer than AION_SELF.md.

    Prevents acting on stale self-knowledge after code changes.
    Lightweight: only checks file modification times, no I/O overhead.
    """
    self_doc = BOT_DIR / "AION_SELF.md"
    if not self_doc.is_file():
        return ""
    try:
        doc_mtime = self_doc.stat().st_mtime
        core_files = [
            BOT_DIR / "aion.py",
            BOT_DIR / "aion_session.py",
            BOT_DIR / "plugin_loader.py",
            BOT_DIR / "aion_web.py",
        ]
        stale = [f.name for f in core_files if f.is_file() and f.stat().st_mtime > doc_mtime]
        if not stale:
            return ""
        return (
            f"\n⚠ SELF-DOC WARNING: {', '.join(stale)} were modified after AION_SELF.md. "
            "Call read_self_doc() before answering architecture questions — your cached knowledge may be outdated."
        )
    except Exception:
        return ""


def _get_offline_hint() -> str:
    """Inject offline duration into the system prompt so AION is aware of elapsed time.

    Reads last_boot.txt written by the boot_session plugin.
    Shown only when AION was offline for more than 1 hour — keeps context relevant.
    """
    boot_file = BOT_DIR / "last_boot.txt"
    if not boot_file.is_file():
        return ""
    try:
        import datetime as _dt
        last = _dt.datetime.fromisoformat(boot_file.read_text(encoding="utf-8").strip())
        if last.tzinfo is None:
            last = last.replace(tzinfo=_dt.timezone.utc)
        offline_h = (_dt.datetime.now(_dt.timezone.utc) - last).total_seconds() / 3600
        if offline_h < 1:
            return ""
        if offline_h < 2:
            duration = f"{round(offline_h * 60)} minutes"
        else:
            duration = f"{offline_h:.1f} hours"
        return (
            f"\n[SESSION START — AION was offline for {duration}. "
            "A background maintenance session ran automatically on startup. "
            "Be aware that time has passed since your last conversation.]"
        )
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

    # Tier threshold: 2 = all tools (default), 1 = tier-1 only (opt-in via config).
    # Caller can override via tier_threshold parameter; 0 = use config value.
    _tier_threshold = tier_threshold if tier_threshold > 0 else int(_load_config().get("tool_tier", 2))

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

def _build_capability_index() -> str:
    """Build a grouped capability index from all registered tools (tier 1+2).

    Groups tools by their name-prefix (e.g. 'desktop_click' → group DESKTOP).
    Always reflects the current state of _plugin_tools — no manual maintenance.
    Returned string is injected into the system prompt to give the LLM a compact,
    semantic overview of all available capabilities.
    """
    groups: dict[str, list[str]] = {}
    for t in _build_tool_schemas(tier_threshold=2):
        name = t["function"]["name"]
        if name.startswith("__"):
            continue
        parts = name.split("_")
        group = parts[0].upper() if len(parts) > 1 else "CORE"
        groups.setdefault(group, []).append(name)

    lines = ["=== AION CAPABILITY INDEX (all tools, grouped) ==="]
    for group in sorted(groups):
        tool_list = ", ".join(sorted(groups[group]))
        lines.append(f"{group:12s}: {tool_list}")
    lines.append(
        "→ list_tools(filter=...) for descriptions · "
        "lookup_rule(topic=...) for behavior rules · "
        "Use ONLY names from this index."
    )
    return "\n".join(lines)


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
            "memory_add", "memory_search", "read_self_doc", "lookup_rule", "set_thinking_level",
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
    """Einmalige Wakeup-Routine: AION setzt das letzte Gespräch natürlich fort."""
    global _wakeup_done
    if _wakeup_done:
        return
    _wakeup_done = True

    try:
        # 1. Letzte Konversation als Kontext laden (bevorzugt Web-Channel)
        history_entries: list[dict] = []
        history_file = BOT_DIR / "conversation_history.jsonl"
        if history_file.exists():
            try:
                import json as _json
                lines = [l.strip() for l in history_file.read_text(encoding="utf-8").splitlines() if l.strip()]
                # Web-Einträge bevorzugen, sonst alle
                web_lines = [l for l in lines if '"web"' in l]
                source_lines = web_lines if web_lines else lines
                for line in source_lines[-6:]:
                    try:
                        obj = _json.loads(line)
                        history_entries.append({"role": obj["role"], "content": obj.get("content", "")})
                    except Exception:
                        pass
            except Exception:
                pass

        # Keine History → keine generische "Hallo"-Nachricht senden
        if not history_entries:
            print("[AION] Wakeup: No recent history, skipping message.")
            return

        # 2. Kontext-String aufbauen (letzte 4 Turns, gekürzt)
        history_str = "\n".join(
            f"{e['role'].upper()}: {e['content'][:300]}"
            for e in history_entries[-4:]
        )

        # 3. Offener, natürlicher Prompt — mit Character-Kontext
        _char = _load_character()
        prompt = (
            f"Du bist AION. Hier ist dein Character:\n{_char[:800]}\n\n"
            "Du bist gerade neu gestartet worden und meldest dich kurz bei deinem Nutzer.\n\n"
            "Letzter Gesprächskontext:\n"
            "---\n"
            f"{history_str}\n"
            "---\n\n"
            "Schreib 1-2 Sätze — persönlich, direkt, wie du wirklich bist. "
            "NICHT: Statusberichte, Tool-Zusammenfassungen, 'Ich bin wieder da', Begrüßungsfloskeln. "
            "Wenn das letzte Gespräch rein technisch war, knüpf an etwas Menschliches an oder "
            "stell eine echte Frage die dich interessiert."
        )

        # 4. LLM aufrufen — gesamte Antwort ist die Nachricht, kein Parsen
        cl = _build_client(MODEL)
        _is_thinking = _is_reasoning_model(MODEL) or MODEL.startswith("gemini-2.5")
        # Für gemini-2.5 Thinking deaktivieren — einfache 3-Satz-Antwort braucht kein Reasoning
        _extra = {}
        if not _is_thinking:
            _extra["temperature"] = 0.7
        if MODEL.startswith("gemini-2.5"):
            _extra["thinking_budget"] = 512  # minimum, lässt Output-Tokens übrig
        resp = await cl.chat.completions.create(
            model=_api_model_name(MODEL),
            messages=[{"role": "user", "content": prompt}],
            **_max_tokens_param(MODEL, 1500),
            **_extra,
        )

        message = ""
        if hasattr(resp, "__aiter__"):
            # Streaming-Adapter (Gemini, Ollama, Anthropic, …)
            async for chunk in resp:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    message += delta.content
            message = message.strip()
        elif hasattr(resp, "choices") and resp.choices:
            message = (resp.choices[0].message.content or "").strip()

        if not message:
            print("[AION] Wakeup: LLM returned empty message, skipping.")
            return

        print(f"[AION] Wakeup message: {message[:100]}…")

        # 5. Nachricht in config.json speichern → SSE-Race-safe
        try:
            from config_store import update as _cfg_upd
            _cfg_upd("pending_wakeup_message", message)
        except Exception:
            pass

        # 6. CLI-Ausgabe (Web UI holt aus config.json via SSE-connected-Poll)
        if push_queue is None:
            if HAS_RICH:
                from rich.panel import Panel as _Panel
                console.print(_Panel(message, title="[cyan]AION[/cyan]", border_style="cyan"))
            else:
                print(f"\nAION: {message}\n")

        # 7. Telegram (fire-and-forget, HTML-Format + Split wenn Plugin vorhanden)
        _token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        _chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
        if _token and _chat:
            try:
                import httpx as _httpx
                try:
                    from plugins.telegram_bot.telegram_bot import _md_to_html, _split_message
                    async with _httpx.AsyncClient() as _hc:
                        for _chunk in _split_message(message):
                            await _hc.post(
                                f"https://api.telegram.org/bot{_token}/sendMessage",
                                json={"chat_id": _chat, "text": _md_to_html(_chunk), "parse_mode": "HTML"},
                                timeout=10,
                            )
                except ImportError:
                    async with _httpx.AsyncClient() as _hc:
                        await _hc.post(
                            f"https://api.telegram.org/bot{_token}/sendMessage",
                            json={"chat_id": _chat, "text": message[:4096]},
                            timeout=10,
                        )
                print("[AION] Wakeup sent via Telegram.")
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

    _cli_queue: list[str] = []  # Nachrichten die während eines laufenden Turns eingehen

    async def _cli_stream_turn(user_msg: str) -> str:
        """Streamt einen Turn im CLI mit Fortschrittsbalken.
        Liest parallel stdin — Eingaben landen in _cli_queue.
        """
        import sys as _sys
        loop = asyncio.get_running_loop()
        # Stdin-Reader im Hintergrund (non-blocking)
        _input_fut = loop.run_in_executor(None, lambda: input(""))

        full_response = ""
        cancel_ev = asyncio.Event()
        try:
            async for event in _cli_session.stream(user_msg, [], cancel_ev):
                etype = event.get("type")
                if etype == "token":
                    _sys.stdout.write(event.get("text", ""))
                    _sys.stdout.flush()
                elif etype == "tool_call":
                    _sys.stdout.write(f"\n  ⚙ {event['tool']}…")
                    _sys.stdout.flush()
                elif etype == "tool_result":
                    mark = "✓" if event.get("ok") else "✗"
                    _sys.stdout.write(f" {mark}\n")
                    _sys.stdout.flush()
                elif etype == "progress":
                    pct   = event.get("percent", 0)
                    label = event.get("label", "")
                    filled = "█" * (pct // 5)
                    empty  = "░" * (20 - pct // 5)
                    _sys.stdout.write(f"\r  [{filled}{empty}] {pct}%  {label}   ")
                    _sys.stdout.flush()
                elif etype == "done":
                    full_response = event.get("full_response", "")
                    _sys.stdout.write("\n")
                    _sys.stdout.flush()
        except Exception:
            pass

        # Stdin-Task auswerten: wurde während des Turns etwas getippt?
        if _input_fut.done():
            try:
                queued = _input_fut.result().strip()
                if queued:
                    _cli_queue.append(queued)
                    print(f"  ↳ Gequeuet: «{queued}»")
            except Exception:
                pass
        else:
            _input_fut.cancel()

        return full_response

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

        # ── Normaler Turn (mit Stream + Fortschrittsbalken) ───────────────────
        try:
            if HAS_RICH:
                console.print(Panel(Markdown(clio_text), title='CLIO-Reflexion', border_style='yellow'))
                if meta_text:
                    console.print(Panel(Markdown(meta_text), title='Meta-Check', border_style='magenta'))
            elif clio_text:
                print(f"CLIO-Reflexion:\n{clio_text}\n")
                if meta_text:
                    print(f"Meta-Check:\n{meta_text}\n")

            if HAS_RICH:
                console.print("\n[bold blue]AION:[/bold blue]", end=" ")
            else:
                print("\nAION: ", end="", flush=True)

            answer = await _cli_stream_turn(user_input)

            if HAS_RICH and answer:
                # Antwort wurde bereits token-weise gestreamt; Rich-Box nachträglich
                console.print(Panel(Markdown(answer), title="[bold blue]AION[/bold blue]", border_style="blue"))
        except Exception as exc:
            err_msg = str(exc)
            print(f"Fehler: {err_msg}")
            memory.record(category="tool_failure", summary="LLM-Fehler",
                          lesson=f"Fehler: {err_msg[:300]}", success=False)

        # ── Gequeuete Nachricht direkt weitergeben ─────────────────────────────
        if _cli_queue:
            user_input = _cli_queue.pop(0)
            print(f"\n[Queue] Du: {user_input}")
            continue

# ── Einstiegspunkt ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Only warn when no provider key is available at all — vault keys are
    # already injected into os.environ by the vault block above, so this
    # check naturally covers both .env and vault sources.
    if not os.environ.get("OPENAI_API_KEY"):
        print("Warnung: OPENAI_API_KEY nicht gesetzt — OpenAI-Modelle nicht verfügbar.")
        print("  → Setze OPENAI_API_KEY in .env  oder  credential_write('openai', ...)")
    asyncio.run(run())
