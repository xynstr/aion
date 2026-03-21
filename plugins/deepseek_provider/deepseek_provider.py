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


def register(api):
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("[Plugin] deepseek_provider: no DEEPSEEK_API_KEY — provider not registered (add to .env to enable)")
        return

    if not hasattr(_aion_module, "register_provider"):
        print("[Plugin] deepseek_provider: aion.py has no register_provider — skipping")
        return

    _aion_module.register_provider(
        prefix=DEEPSEEK_PREFIX,
        build_fn=_build_client,
        label="DeepSeek",
        models=KNOWN_MODELS,
    )

    print(f"[Plugin] deepseek_provider loaded — models: {', '.join(KNOWN_MODELS)}")
