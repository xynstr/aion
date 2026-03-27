"""
AION Plugin: DeepSeek Provider
================================
Connects to DeepSeek's API (https://platform.deepseek.com).
Uses the OpenAI-compatible endpoint — same SDK, different base_url.

Setup:
  DEEPSEEK_API_KEY=sk-...   in .env

Models:
  deepseek-chat      — DeepSeek V3, best for general tasks (fast, cheap)
  deepseek-reasoner  — DeepSeek R1, best for reasoning/math/code

Usage:
  switch_model("deepseek-chat")
  switch_model("deepseek-reasoner")
"""

import os
import aion as _aion_module

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_PREFIX   = "deepseek"

KNOWN_MODELS = [
    "deepseek-chat",
    "deepseek-reasoner",
]


def _build_client(model: str):
    from openai import AsyncOpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set in .env")
    return AsyncOpenAI(base_url=DEEPSEEK_BASE_URL, api_key=api_key)


async def _list_deepseek_models_dynamic():
    """Ruft verfügbare DeepSeek-Modelle live von der API ab (OpenAI-compatible /v1/models)."""
    try:
        import httpx
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            return KNOWN_MODELS
        async with httpx.AsyncClient(timeout=4.0) as c:
            r = await c.get(
                f"{DEEPSEEK_BASE_URL}/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if r.status_code == 200:
                data   = r.json()
                models = [m["id"] for m in data.get("data", []) if m.get("id")]
                return models if models else KNOWN_MODELS
    except Exception:
        pass
    return KNOWN_MODELS


def register(api):
    # Vault fallback: inject into os.environ so _build_client + model listing pick it up.
    # Store with: credential_write("deepseek", "- DEEPSEEK_API_KEY: sk-...")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        try:
            from plugins.credentials.credentials import _vault_read_key_sync
            _v = _vault_read_key_sync("deepseek", "DEEPSEEK_API_KEY")
            if _v:
                os.environ["DEEPSEEK_API_KEY"] = _v
        except Exception:
            pass

    # Immer registrieren — API-Key-Prüfung erfolgt zur Laufzeit via _model_available()
    if not hasattr(_aion_module, "register_provider"):
        print("[Plugin] deepseek_provider: aion.py has no register_provider — skipping")
        return

    _aion_module.register_provider(
        prefix=DEEPSEEK_PREFIX,
        build_fn=_build_client,
        label="DeepSeek",
        models=KNOWN_MODELS,
        env_keys=["DEEPSEEK_API_KEY"],
        context_window=64_000,
        list_models_fn=_list_deepseek_models_dynamic,
    )

    print(f"[Plugin] deepseek_provider loaded — models: {', '.join(KNOWN_MODELS)}")
