"""
AION Web UI — FastAPI + SSE Live-Stream
Starten:
  pip install fastapi uvicorn httpx
  set OPENAI_API_KEY=sk-...
  python aion_web.py
Öffnen: http://localhost:7000
"""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

AION_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(AION_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(AION_DIR / ".env")
except ImportError:
    pass

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
    import uvicorn
except ImportError:
    print("Bitte installieren: pip install fastapi uvicorn")
    sys.exit(1)

import aion as _aion_module
from aion import memory, _dispatch, _load_character, AionSession, BOT_DIR

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_FILE = AION_DIR / "config.json"

def _load_config() -> dict:
    if CONFIG_FILE.is_file():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def _get_model() -> str:
    cfg = _load_config()
    return cfg.get("model", os.environ.get("AION_MODEL", "gpt-4.1"))

def _set_model(model: str):
    cfg = _load_config()
    cfg["model"] = model
    _save_config(cfg)
    _aion_module.MODEL = model
    if hasattr(_aion_module, "_build_client"):
        _aion_module.client = _aion_module._build_client(model)
    else:
        from openai import AsyncOpenAI
        _aion_module.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

_startup_model = _get_model()

# ── Session ───────────────────────────────────────────────────────────────────

_session = AionSession(channel="web")

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: Modell setzen + History aus vorheriger Sitzung laden."""
    m = _startup_model
    _aion_module.MODEL = m
    if hasattr(_aion_module, "_build_client"):
        _aion_module.client = _aion_module._build_client(m)
    print(f"[AION] Startup-Modell: {m}")
    await _session.load_history(num_entries=20)
    yield

app = FastAPI(title="AION", lifespan=_lifespan)

# ── SSE-Adapter ───────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

async def _stream_chat(user_input: str) -> AsyncGenerator[str, None]:
    """Konvertiert AionSession-Events in SSE-Strings für den Browser."""
    async for event in _session.stream(user_input):
        yield _sse(event)

# ── API-Routen ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    p = AION_DIR / "static" / "index.html"
    if p.is_file():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>index.html nicht gefunden</h1>", status_code=404)

async def _stream_chat_with_images(user_input: str, images: list | None) -> AsyncGenerator[str, None]:
    async for event in _session.stream(user_input, images=images):
        yield _sse(event)

@app.post("/api/chat")
async def chat(request: Request):
    body       = await request.json()
    user_input = body.get("message", "").strip()
    # Optionale Bilder als Liste von Base64-Data-URLs oder öffentlichen URLs
    images     = body.get("images") or None
    if not user_input and not images:
        return JSONResponse({"error": "Leere Nachricht"}, status_code=400)
    return StreamingResponse(
        _stream_chat_with_images(user_input, images),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )

@app.post("/api/reset")
async def reset():
    _session.messages       = []
    _session.exchange_count = 0
    _session._client        = None
    return JSONResponse({"ok": True})

@app.get("/api/status")
async def status():
    return JSONResponse({
        "model":            _aion_module.MODEL,
        "memory_entries":   len(memory._entries),
        "conversation_len": len(_session.messages),
        "character":        _load_character()[:500],
    })

@app.post("/api/model")
async def set_model(request: Request):
    body  = await request.json()
    model = body.get("model", "").strip()
    if not model:
        return JSONResponse({"error": "Kein Modell angegeben"}, status_code=400)
    _set_model(model)
    _session._client = None  # Session-Client zurücksetzen — neues Modell beim nächsten Turn
    memory.record(
        category="user_preference",
        summary=f"Modell gewechselt zu {model}",
        lesson=f"Nutzer hat Modell auf {model} geändert",
        success=True,
    )
    provider = "gemini" if model.startswith("gemini") else "openai"
    return JSONResponse({"ok": True, "model": model, "provider": provider})

@app.get("/api/character")
async def get_character():
    return JSONResponse({"character": _load_character()})

if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Fehler: OPENAI_API_KEY nicht gesetzt.")
        sys.exit(1)
    print(f"Starte AION Web UI auf http://localhost:7000")
    print(f"Modell: {_aion_module.MODEL}")
    print("Beenden: Strg+C\n")
    uvicorn.run(app, host="0.0.0.0", port=7000, log_level="warning")
