"""
AION Plugin: Ollama Provider
=============================
Runs local LLMs via Ollama (https://ollama.com).
Uses Ollama's OpenAI-compatible API — no API key needed.

Setup:
  1. Install Ollama: https://ollama.com/download
  2. Pull a model:   ollama pull llama3.2
  3. Start Ollama:   ollama serve   (or it starts automatically)
  4. Use in AION:    switch_model("ollama/llama3.2")

Model name format: "ollama/<model>" — e.g.:
  ollama/llama3.2         (Meta Llama 3.2, 3B)
  ollama/llama3.1:8b      (Meta Llama 3.1, 8B)
  ollama/mistral          (Mistral 7B)
  ollama/qwen2.5          (Alibaba Qwen 2.5)
  ollama/deepseek-r1:8b   (DeepSeek R1 distilled)
  ollama/phi4             (Microsoft Phi-4)
  ollama/gemma3           (Google Gemma 3)
  ollama/codellama        (Meta Code Llama)

Config (.env or config.json):
  OLLAMA_BASE_URL=http://localhost:11434  (default)
"""

import os
import aion as _aion_module

OLLAMA_PREFIX   = "ollama/"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

KNOWN_MODELS = [
    "ollama/llama3.2",
    "ollama/llama3.1:8b",
    "ollama/mistral",
    "ollama/qwen2.5",
    "ollama/deepseek-r1:8b",
    "ollama/phi4",
    "ollama/gemma3",
    "ollama/codellama",
]


def _build_client(model: str):
    """Returns an OpenAI-compatible client pointing at the local Ollama server."""
    from openai import AsyncOpenAI
    # Strip the "ollama/" prefix — Ollama uses bare model names
    return AsyncOpenAI(
        base_url=f"{OLLAMA_BASE_URL.rstrip('/')}/v1",
        api_key="ollama",   # Ollama ignores the key but the SDK requires a non-empty value
    )


def _ollama_list(params: dict = None) -> dict:
    """Lists models currently available in the local Ollama installation."""
    import httpx
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "models": models, "base_url": OLLAMA_BASE_URL}
        return {"ok": False, "error": f"HTTP {r.status_code}", "base_url": OLLAMA_BASE_URL}
    except Exception as e:
        return {"ok": False, "error": str(e), "hint": "Is Ollama running? Try: ollama serve"}


def register(api):
    if not hasattr(_aion_module, "register_provider"):
        print("[Plugin] ollama_provider: aion.py has no register_provider — skipping")
        return

    _aion_module.register_provider(
        prefix=OLLAMA_PREFIX,
        build_fn=_build_client,
        label="Ollama (local)",
        models=KNOWN_MODELS,
    )

    api.register_tool(
        name="ollama_list_models",
        description=(
            "Lists all models currently available in the local Ollama installation. "
            "Use this to see what you can switch to with switch_model('ollama/<name>')."
        ),
        func=_ollama_list,
        input_schema={"type": "object", "properties": {}},
    )

    print(f"[Plugin] ollama_provider loaded — base_url: {OLLAMA_BASE_URL} | prefix: {OLLAMA_PREFIX}")
