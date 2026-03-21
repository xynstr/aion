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
import re
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
            return {}
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

# ── Plugin-Router einbinden ───────────────────────────────────────────────────
# Plugins können in register() eigene FastAPI-Router via api.register_router()
# anmelden. Diese werden hier (und nach jedem Hot-Reload) in die App eingebunden.

_included_router_ids: set = set()

def _include_plugin_routers():
    """Bindet alle noch nicht eingebundenen Plugin-Router in die FastAPI-App ein."""
    from plugin_loader import _pending_routers
    for router, prefix, tags in _pending_routers:
        rid = id(router)
        if rid not in _included_router_ids:
            app.include_router(router, prefix=prefix, tags=tags)
            _included_router_ids.add(rid)

# Plugins wurden bereits beim `import aion` geladen — Router direkt einbinden
_include_plugin_routers()

# ── SSE-Adapter ───────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

async def _stream_chat(user_input: str) -> AsyncGenerator[str, None]:
    """Konvertiert AionSession-Events in SSE-Strings für den Browser."""
    async for event in _session.stream(user_input):
        yield _sse(event)

# ── API-Routen ────────────────────────────────────────────────────────────────

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # Inline-SVG als Data-URL — kein extra File nötig
    from fastapi.responses import Response
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<rect width="32" height="32" rx="6" fill="#0d1117"/>'
        '<text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" '
        'font-size="20" font-family="monospace" fill="#00e5ff">A</text>'
        '</svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")

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

@app.get("/api/history")
async def history():
    msgs = []
    for m in _session.messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        if content:
            msgs.append({"role": role, "content": content})
    return JSONResponse({"messages": msgs})

@app.get("/api/character")
async def get_character():
    return JSONResponse({"character": _load_character()})

# ── Prompt-Editor API ──────────────────────────────────────────────────────────

_PROMPT_FILES = {
    "rules":     AION_DIR / "prompts" / "rules.md",
    "character": AION_DIR / "character.md",
    "self_doc":  AION_DIR / "AION_SELF.md",
}

@app.get("/api/prompt/{name}")
async def get_prompt(name: str):
    path = _PROMPT_FILES.get(name)
    if path is None:
        return JSONResponse({"error": f"Unbekannte Prompt-Datei: {name}"}, status_code=404)
    try:
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        return JSONResponse({"name": name, "content": content, "path": str(path)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/prompt/{name}")
async def save_prompt(name: str, request: Request):
    path = _PROMPT_FILES.get(name)
    if path is None:
        return JSONResponse({"error": f"Unbekannte Prompt-Datei: {name}"}, status_code=404)
    try:
        body    = await request.json()
        content = body.get("content", "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return JSONResponse({"ok": True, "name": name, "bytes": len(content)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ── Plugins API ────────────────────────────────────────────────────────────────

@app.get("/api/plugins")
async def list_plugins():
    plugins_dir = AION_DIR / "plugins"
    all_tools   = {
        name: {"description": data.get("description", ""), "schema": data.get("schema", {})}
        for name, data in _aion_module._plugin_tools.items()
        if not name.startswith("__")
    }
    plugins = []
    if plugins_dir.is_dir():
        for plugin_dir in sorted(plugins_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            if plugin_dir.name.startswith("_") or plugin_dir.name.startswith("."):
                continue
            plugin_file = plugin_dir / f"{plugin_dir.name}.py"
            if not plugin_file.is_file():
                continue
            try:
                source     = plugin_file.read_text(encoding="utf-8", errors="replace")
                tool_names = re.findall(r'register_tool\s*\(\s*name\s*=\s*["\']([^"\']+)["\']', source)
            except Exception:
                tool_names = []
            tools_info = []
            for tname in tool_names:
                entry = {"name": tname, "loaded": tname in all_tools}
                if tname in all_tools:
                    entry["description"] = all_tools[tname]["description"]
                tools_info.append(entry)
            plugins.append({
                "name":   plugin_dir.name,
                "file":   str(plugin_file),
                "tools":  tools_info,
                "loaded": any(t["loaded"] for t in tools_info) if tools_info else False,
            })
    # Tools ohne zugeordnetes Plugin (z.B. via create_plugin flach registriert)
    assigned = {t["name"] for p in plugins for t in p["tools"]}
    orphans  = [{"name": n, "loaded": True, "description": d["description"]}
                for n, d in all_tools.items() if n not in assigned]
    return JSONResponse({
        "plugins":     plugins,
        "orphan_tools": orphans,
        "total_loaded": len(all_tools),
    })

@app.post("/api/plugins/reload")
async def reload_plugins():
    try:
        from plugin_loader import load_plugins
        load_plugins(_aion_module._plugin_tools)
        _include_plugin_routers()   # neu registrierte Router sofort einbinden
        tools = [n for n in _aion_module._plugin_tools if not n.startswith("__")]
        return JSONResponse({"ok": True, "tools": tools, "count": len(tools)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ── Memory API ──────────────────────────────────────────────────────────────────

@app.get("/api/memory")
async def list_memory(search: str = "", limit: int = 80):
    memory_file = AION_DIR / "aion_memory.json"
    try:
        entries = json.loads(memory_file.read_text(encoding="utf-8")) if memory_file.is_file() else []
    except Exception:
        entries = []
    total = len(entries)
    if search:
        q = search.lower()
        entries = [e for e in entries
                   if q in e.get("summary", "").lower()
                   or q in e.get("lesson",  "").lower()
                   or q in e.get("category","").lower()]
    entries = list(reversed(entries))[:limit]
    return JSONResponse({"entries": entries, "total": total, "returned": len(entries)})

@app.delete("/api/memory")
async def clear_memory():
    memory_file = AION_DIR / "aion_memory.json"
    try:
        memory_file.write_text("[]", encoding="utf-8")
        _aion_module.memory._entries.clear()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ── Config API ──────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    cfg = _load_config()
    return JSONResponse({
        "model":          _aion_module.MODEL,
        "bot_dir":        str(AION_DIR),
        "memory_entries": len(_aion_module.memory._entries),
        "exchange_count": int(cfg.get("exchange_count", 0)),
        "config":         {k: v for k, v in cfg.items() if k != "model"},
    })

@app.post("/api/config/reset_exchanges")
async def reset_exchanges():
    cfg = _load_config()
    cfg["exchange_count"] = 0
    _save_config(cfg)
    _session.exchange_count = 0
    return JSONResponse({"ok": True})

if __name__ == "__main__":
    has_key = bool(os.environ.get("OPENAI_API_KEY", "").strip()) or \
              bool(os.environ.get("GEMINI_API_KEY", "").strip())
    if not has_key:
        print("Fehler: Kein API-Key gesetzt (OPENAI_API_KEY oder GEMINI_API_KEY fehlt).")
        sys.exit(1)
    print(f"Starte AION Web UI auf http://localhost:7000")
    print(f"Modell: {_aion_module.MODEL}")
    print("Beenden: Strg+C\n")
    uvicorn.run(app, host="0.0.0.0", port=7000, log_level="warning")
