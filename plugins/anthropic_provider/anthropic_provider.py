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
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
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


def register(api):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[Plugin] anthropic_provider: no ANTHROPIC_API_KEY — provider not registered (add to .env to enable)")
        return

    if not hasattr(_aion_module, "register_provider"):
        print("[Plugin] anthropic_provider: aion.py has no register_provider — skipping")
        return

    _aion_module.register_provider(
        prefix=ANTHROPIC_PREFIX,
        build_fn=_build_client,
        label="Anthropic Claude",
        models=KNOWN_MODELS,
    )

    print(f"[Plugin] anthropic_provider loaded — models: {', '.join(KNOWN_MODELS[:3])} …")
