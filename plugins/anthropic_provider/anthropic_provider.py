"""
AION Plugin: Anthropic Provider (Claude)
==========================================
Connects to Anthropic's Claude API.
Uses Anthropic's OpenAI-compatible endpoint so no extra SDK is needed.

Setup:
  ANTHROPIC_API_KEY=sk-ant-...   in .env

Models:
  claude-opus-4-6           — Claude Opus 4.6, most capable
  claude-sonnet-4-6         — Claude Sonnet 4.6, best balance (recommended)
  claude-haiku-4-5-20251001 — Claude Haiku 4.5, fastest & cheapest

Usage:
  switch_model("claude-sonnet-4-6")
  switch_model("claude-opus-4-6")

Note:
  Claude supports tool use and vision.
  Context window: up to 200k tokens depending on model.
  Anthropic's API is OpenAI-compatible at https://api.anthropic.com/v1
  so no additional SDK installation is required.
"""

import os
import aion as _aion_module

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_PREFIX   = "claude"

KNOWN_MODELS = [
    # Claude 4.x (neueste Generation)
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    # Claude 3.x
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307",
]


def _build_client(model: str):
    from openai import AsyncOpenAI
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
    return AsyncOpenAI(
        base_url=ANTHROPIC_BASE_URL,
        api_key=api_key,
        default_headers={
            "anthropic-version": "2023-06-01",
            "anthropic-beta":    "tools-2024-04-04",
        },
    )


async def _list_anthropic_models_dynamic():
    """Ruft verfügbare Claude-Modelle live von der Anthropic API ab.
    Endpoint: GET https://api.anthropic.com/v1/models (paginiert, max 100)"""
    try:
        import httpx
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return KNOWN_MODELS
        async with httpx.AsyncClient(timeout=4.0) as c:
            r = await c.get(
                f"{ANTHROPIC_BASE_URL}/models",
                headers={
                    "x-api-key":         api_key,
                    "anthropic-version": "2023-06-01",
                },
                params={"limit": 100},
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
    # Store with: credential_write("anthropic", "- ANTHROPIC_API_KEY: sk-ant-...")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from plugins.credentials.credentials import _vault_read_key_sync
            _v = _vault_read_key_sync("anthropic", "ANTHROPIC_API_KEY")
            if _v:
                os.environ["ANTHROPIC_API_KEY"] = _v
        except Exception:
            pass

    # Immer registrieren — API-Key-Prüfung erfolgt zur Laufzeit via _model_available()
    if not hasattr(_aion_module, "register_provider"):
        print("[Plugin] anthropic_provider: aion.py has no register_provider — skipping")
        return

    _aion_module.register_provider(
        prefix=ANTHROPIC_PREFIX,
        build_fn=_build_client,
        label="Anthropic Claude",
        models=KNOWN_MODELS,
        env_keys=["ANTHROPIC_API_KEY"],
        context_window=200_000,
        list_models_fn=_list_anthropic_models_dynamic,
    )

    print(f"[Plugin] anthropic_provider loaded — models: {', '.join(KNOWN_MODELS[:3])} …")
