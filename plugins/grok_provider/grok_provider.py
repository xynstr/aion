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
    "grok-3-mini",
    "grok-2",
    "grok-beta",
]


def _build_client(model: str):
    from openai import AsyncOpenAI
    api_key = os.environ.get("XAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("XAI_API_KEY not set in .env")
    return AsyncOpenAI(base_url=GROK_BASE_URL, api_key=api_key)


def register(api):
    api_key = os.environ.get("XAI_API_KEY", "")
    if not api_key:
        print("[Plugin] grok_provider: no XAI_API_KEY — provider not registered (add to .env to enable)")
        return

    if not hasattr(_aion_module, "register_provider"):
        print("[Plugin] grok_provider: aion.py has no register_provider — skipping")
        return

    _aion_module.register_provider(
        prefix=GROK_PREFIX,
        build_fn=_build_client,
        label="xAI Grok",
        models=KNOWN_MODELS,
    )

    print(f"[Plugin] grok_provider loaded — models: {', '.join(KNOWN_MODELS)}")
