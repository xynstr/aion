"""
AION Plugin: Grok Provider (xAI)
==================================
Connects to xAI's Grok API (https://console.x.ai).
Uses the OpenAI-compatible endpoint.

Setup:
  XAI_API_KEY=xai-...   in .env

Models:
  grok-3          — Grok 3, flagship model
  grok-3-mini     — Grok 3 Mini, fast & cheap
  grok-2          — Grok 2 (previous gen)
  grok-beta       — Latest beta

Usage:
  switch_model("grok-3")
  switch_model("grok-3-mini")
"""

import os
import aion as _aion_module

GROK_BASE_URL = "https://api.x.ai/v1"
GROK_PREFIX   = "grok"

KNOWN_MODELS = [
    "grok-3",
    "grok-3-fast",
    "grok-3-mini",
    "grok-3-mini-fast",
    "grok-2-1212",
    "grok-2",
    "grok-beta",
]


def _build_client(model: str):
    from openai import AsyncOpenAI
    api_key = os.environ.get("XAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("XAI_API_KEY not set in .env")
    return AsyncOpenAI(base_url=GROK_BASE_URL, api_key=api_key)


async def _list_grok_models_dynamic():
    """Ruft verfügbare xAI Grok-Modelle live von der API ab (OpenAI-compatible /v1/models)."""
    try:
        import httpx
        api_key = os.environ.get("XAI_API_KEY", "")
        if not api_key:
            return KNOWN_MODELS
        async with httpx.AsyncClient(timeout=4.0) as c:
            r = await c.get(
                f"{GROK_BASE_URL}/models",
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
    # Store with: credential_write("grok", "- XAI_API_KEY: xai-...")
    if not os.environ.get("XAI_API_KEY"):
        try:
            from plugins.credentials.credentials import _vault_read_key_sync
            _v = _vault_read_key_sync("grok", "XAI_API_KEY")
            if _v:
                os.environ["XAI_API_KEY"] = _v
        except Exception:
            pass

    # Immer registrieren — API-Key-Prüfung erfolgt zur Laufzeit via _model_available()
    if not hasattr(_aion_module, "register_provider"):
        print("[Plugin] grok_provider: aion.py has no register_provider — skipping")
        return

    _aion_module.register_provider(
        prefix=GROK_PREFIX,
        build_fn=_build_client,
        label="xAI Grok",
        models=KNOWN_MODELS,
        env_keys=["XAI_API_KEY"],
        context_window=131_072,
        list_models_fn=_list_grok_models_dynamic,
    )

    print(f"[Plugin] grok_provider loaded — models: {', '.join(KNOWN_MODELS)}")
