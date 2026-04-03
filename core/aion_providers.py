"""
aion_providers — Provider Registry und LLM-Client-Routing für AION.
Extrahiert aus aion.py.
"""
import os

from openai import AsyncOpenAI

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
    # Dedup: in-place mutieren statt neu zuweisen — damit alle Referenzen (aion.py etc.)
    # auf dieselbe Liste zeigen und die Änderung sehen.
    _provider_registry[:] = [e for e in _provider_registry if e["prefix"] != prefix]
    _provider_registry.append({
        "prefix":         prefix,
        "build_fn":       build_fn,
        "label":          label or prefix,
        "models":         models or [],
        "env_keys":       env_keys or [],
        "context_window": context_window,
        "list_models_fn": list_models_fn,
    })


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
_CHEAP_CHECK_MODELS: dict[str, str] = {
    "gemini":    "gemini-2.5-flash",
    "gpt-":      "gpt-4.1-mini",
    "chatgpt-":  "gpt-4.1-mini",
    "o1":        "gpt-4.1-mini",
    "o3":        "gpt-4.1-mini",
    "o4":        "gpt-4.1-mini",
    "claude":    "claude-haiku-4-5-20251001",
    "deepseek":  "deepseek-chat",
    "grok":      "grok-3-mini",
}
