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
import config_store as _cfg_store

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_FILE = AION_DIR / "config.json"

def _load_config() -> dict:
    return _cfg_store.load()

def _save_config(cfg: dict):
    _cfg_store.save(cfg)

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
    # System-Prompt-Cache invalidieren: Modell-Name ist Teil des Cache-Keys
    if hasattr(_aion_module, "invalidate_sys_prompt_cache"):
        _aion_module.invalidate_sys_prompt_cache()

_startup_model = _get_model()

# ── Session ───────────────────────────────────────────────────────────────────

_session = AionSession(channel="web")
# Pro-Request Cancel-Events statt einem globalen — verhindert Race Conditions
# bei gleichzeitigen Anfragen (key = Task-Objekt-ID → asyncio.Event)
_active_cancel_events: dict[int, asyncio.Event] = {}

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: Modell setzen + History aus vorheriger Sitzung laden."""
    m = _startup_model
    _aion_module.MODEL = m
    if hasattr(_aion_module, "_build_client"):
        _aion_module.client = _aion_module._build_client(m)
    print(f"[AION] Startup-Modell: {m}")
    await _session.load_history(num_entries=20, channel_filter="web")
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

# ── Server-Push Queue (proactive suggestions, notifications) ──────────────────
# Plugins import this via: import aion_web as _web; _web._push_queue.put_nowait(...)
_push_queue: asyncio.Queue = asyncio.Queue()

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

@app.get("/aion-2026.svg", include_in_schema=False)
async def logo_svg():
    from fastapi.responses import Response
    p = AION_DIR / "static" / "aion-2026.svg"
    if p.is_file():
        return Response(content=p.read_bytes(), media_type="image/svg+xml")
    return Response(status_code=404)

@app.get("/aion-2026-small.svg", include_in_schema=False)
async def logo_small_svg():
    from fastapi.responses import Response
    p = AION_DIR / "static" / "aion-2026-small.svg"
    if p.is_file():
        return Response(content=p.read_bytes(), media_type="image/svg+xml")
    return Response(status_code=404)

@app.get("/lucide.min.js", include_in_schema=False)
async def lucide_js():
    from fastapi.responses import Response
    p = AION_DIR / "static" / "lucide.min.js"
    if p.is_file():
        return Response(content=p.read_bytes(), media_type="text/javascript")
    return Response(status_code=404)

@app.get("/", response_class=HTMLResponse)
async def index():
    p = AION_DIR / "static" / "index.html"
    if p.is_file():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>index.html nicht gefunden</h1>", status_code=404)

async def _stream_chat_with_images(user_input: str, images: list | None) -> AsyncGenerator[str, None]:
    task_id = id(asyncio.current_task())
    cancel_event = asyncio.Event()
    _active_cancel_events[task_id] = cancel_event
    try:
        async for event in _session.stream(user_input, images=images, cancel_event=cancel_event):
            yield _sse(event)
    except Exception as e:
        yield _sse({"type": "error", "text": f"[AION Fehler] {e}"})
    finally:
        _active_cancel_events.pop(task_id, None)

@app.post("/api/chat")
async def chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
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

@app.get("/api/events")
async def event_stream(request: Request):
    """Persistent SSE connection for server-initiated push (proactive suggestions, notifications).
    Heartbeat every 30 s keeps the connection alive through proxies.
    """
    async def _generate() -> AsyncGenerator[str, None]:
        yield _sse({"type": "connected", "message": "AION push stream active"})
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(_push_queue.get(), timeout=30)
                yield _sse(msg)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"   # SSE comment line keeps connection alive
    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )

@app.post("/api/stop")
async def stop_generation():
    if _active_cancel_events:
        # Neueste aktive Anfrage stoppen (last inserted in OrderedDict-Iteration)
        last_event = next(reversed(_active_cancel_events.values()))
        last_event.set()
        return JSONResponse({"ok": True, "stopped": True})
    return JSONResponse({"ok": True, "stopped": False})

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
        "character":        (_load_character() or "")[:500],
    })

@app.post("/api/model")
async def set_model(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
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
    if model.startswith("gemini"):        provider = "gemini"
    elif model.startswith("claude"):      provider = "anthropic"
    elif model.startswith("ollama/"):     provider = "ollama"
    elif model.startswith("deepseek"):    provider = "deepseek"
    elif model.startswith("grok"):        provider = "xai"
    else:                                  provider = "openai"
    return JSONResponse({"ok": True, "model": model, "provider": provider})

@app.get("/api/history")
async def history(channel: str = ""):
    # If a non-web channel is requested, read from persistent history file
    if channel and channel != "web":
        hist_file = AION_DIR / "conversation_history.jsonl"
        msgs: list = []
        if hist_file.is_file():
            try:
                for line in hist_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("channel") != channel:
                            continue
                        role = entry.get("role", "")
                        if role not in ("user", "assistant"):
                            continue
                        content = str(entry.get("content", ""))
                        if content:
                            msgs.append({"role": role, "content": content})
                    except Exception:
                        pass
            except Exception:
                pass
        return JSONResponse({"messages": msgs[-100:]})

    # Default: current web session (in-memory)
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


@app.get("/api/channels")
async def list_channels():
    """Returns all channels with message history, sorted by last activity."""
    hist_file = AION_DIR / "conversation_history.jsonl"
    channels: dict = {}
    if hist_file.is_file():
        try:
            for line in hist_file.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    ch = entry.get("channel", "web")
                    if ch not in channels:
                        channels[ch] = {"id": ch, "count": 0, "last_ts": "", "last_msg": ""}
                    channels[ch]["count"] += 1
                    ts = entry.get("ts", "")
                    if ts:
                        channels[ch]["last_ts"] = ts
                    if entry.get("role") == "user":
                        raw = str(entry.get("content", ""))
                        channels[ch]["last_msg"] = raw[:80]
                except Exception:
                    pass
        except Exception:
            pass

    # Always include web channel
    if "web" not in channels:
        channels["web"] = {"id": "web", "count": 0, "last_ts": "", "last_msg": ""}

    # Nur sinnvolle Kanäle anzeigen:
    # - "web" immer
    # - platform_CHATID (z.B. telegram_123456789, discord_...) — mit konkreter ID
    # Generische/Legacy-Einträge wie "telegram", "discord", "default" werden ignoriert
    _KNOWN_PREFIXES = ("telegram_", "discord_", "slack_", "alexa_")
    result = []
    for ch_id, ch_data in sorted(channels.items(), key=lambda x: x[1]["last_ts"], reverse=True):
        if ch_id == "web":
            label = "Web"
        elif any(ch_id.startswith(p) for p in _KNOWN_PREFIXES):
            suffix = ch_id.split("_", 1)[1]
            platform = ch_id.split("_", 1)[0].capitalize()
            label = f"{platform} · {suffix}"
        else:
            continue  # "default", "telegram", "discord" ohne ID überspringen
        result.append({**ch_data, "label": label})
    return JSONResponse({"channels": result})

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
    from plugin_loader import get_disabled
    plugins_dir = AION_DIR / "plugins"
    all_tools   = {
        name: {"description": data.get("description", ""), "schema": data.get("schema", {})}
        for name, data in _aion_module._plugin_tools.items()
        if not name.startswith("__")
    }
    disabled = get_disabled()
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
                has_register = "def register(" in source
            except Exception:
                tool_names = []
                has_register = False
            tools_info = []
            for tname in tool_names:
                entry = {"name": tname, "loaded": tname in all_tools}
                if tname in all_tools:
                    entry["description"] = all_tools[tname]["description"]
                tools_info.append(entry)
            is_disabled = plugin_dir.name in disabled
            # Plugin is loaded if it has tools OR has a register() function (service plugin)
            is_loaded = (not is_disabled) and (
                (any(t["loaded"] for t in tools_info) if tools_info else False) or has_register
            )
            plugins.append({
                "name":     plugin_dir.name,
                "file":     str(plugin_file),
                "tools":    tools_info,
                "loaded":   is_loaded,
                "disabled": is_disabled,
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

@app.post("/api/plugins/disable")
async def disable_plugin_route(req: Request):
    from plugin_loader import disable_plugin, load_plugins
    data = await req.json()
    name = data.get("name", "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "name required"}, status_code=400)
    disable_plugin(name)
    load_plugins(_aion_module._plugin_tools)
    if hasattr(_aion_module, "invalidate_sys_prompt_cache"):
        _aion_module.invalidate_sys_prompt_cache()
    return JSONResponse({"ok": True, "disabled": name})

@app.post("/api/plugins/enable")
async def enable_plugin_route(req: Request):
    from plugin_loader import enable_plugin, load_plugins
    data = await req.json()
    name = data.get("name", "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "name required"}, status_code=400)
    enable_plugin(name)
    load_plugins(_aion_module._plugin_tools)
    _include_plugin_routers()
    if hasattr(_aion_module, "invalidate_sys_prompt_cache"):
        _aion_module.invalidate_sys_prompt_cache()
    return JSONResponse({"ok": True, "enabled": name})

@app.post("/api/plugins/reload")
async def reload_plugins():
    try:
        from plugin_loader import load_plugins
        load_plugins(_aion_module._plugin_tools)
        _include_plugin_routers()   # neu registrierte Router sofort einbinden
        # System-Prompt-Cache invalidieren: Plugin-Anzahl ist Teil des Cache-Keys
        if hasattr(_aion_module, "invalidate_sys_prompt_cache"):
            _aion_module.invalidate_sys_prompt_cache()
        tools = [n for n in _aion_module._plugin_tools if not n.startswith("__")]
        return JSONResponse({"ok": True, "tools": tools, "count": len(tools)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ── Memory API ──────────────────────────────────────────────────────────────────

@app.get("/api/memory")
async def list_memory(search: str = "", limit: int = 80, offset: int = 0):
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
    entries_sorted = list(reversed(entries))
    page = entries_sorted[offset:offset + limit]
    return JSONResponse({
        "entries":  page,
        "total":    total,
        "returned": len(page),
        "has_more": (offset + limit) < len(entries_sorted),
    })

@app.delete("/api/memory")
async def clear_memory():
    memory_file = AION_DIR / "aion_memory.json"
    try:
        memory_file.write_text("[]", encoding="utf-8")
        _aion_module.memory._entries.clear()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ── Keys API ────────────────────────────────────────────────────────────────────

_WELL_KNOWN_KEYS = [
    {"key": "OPENAI_API_KEY",     "label": "OpenAI"},
    {"key": "TELEGRAM_BOT_TOKEN", "label": "Telegram"},
    {"key": "TELEGRAM_CHAT_ID",   "label": "Telegram"},
]

def _mask_key(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 8:
        return "●" * len(val)
    return val[:4] + "…" + val[-4:]


def _read_env_file() -> dict[str, str]:
    """Liest nur AION's .env-Datei direkt (ignoriert System-Umgebungsvariablen).
    Gibt key→value-Paare zurück. Leere Werte werden als nicht gesetzt behandelt."""
    env_file = AION_DIR / ".env"
    result: dict[str, str] = {}
    if not env_file.is_file():
        return result
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v.strip()
    return result


@app.get("/api/keys")
async def get_keys():
    """Returns all known API keys (masked) grouped by provider.
    'set'-Status wird ausschliesslich aus AION's .env-Datei bestimmt,
    nicht aus System-Umgebungsvariablen — verhindert Falsch-Positive bei
    frischer Installation wenn ein Key bereits im System-Env vorhanden ist."""
    registry      = getattr(_aion_module, "_provider_registry", [])
    env_file_keys = _read_env_file()   # Nur .env, nicht os.environ
    covered       = set()
    providers     = []

    for entry in registry:
        env_keys = entry.get("env_keys", [])
        if not env_keys:
            continue
        keys_info = []
        for k in env_keys:
            file_val = env_file_keys.get(k, "")
            sys_val  = os.environ.get(k, "")
            # Als "gesetzt" gilt nur ein nicht-leerer Wert in AION's .env
            is_set   = bool(file_val.strip())
            # Für Anzeige: .env-Wert bevorzugen, sonst System-Wert
            display  = file_val or sys_val
            keys_info.append({"key": k, "set": is_set, "masked": _mask_key(display)})
            covered.add(k)
        providers.append({
            "label":    entry.get("label", entry.get("prefix", "?")),
            "env_keys": keys_info,
        })

    # OpenAI fallback (not in registry, always shown)
    oai_file = env_file_keys.get("OPENAI_API_KEY", "")
    oai_sys  = os.environ.get("OPENAI_API_KEY", "")
    if "OPENAI_API_KEY" not in covered:
        providers.append({
            "label":    "OpenAI",
            "env_keys": [{"key": "OPENAI_API_KEY",
                          "set": bool(oai_file.strip()),
                          "masked": _mask_key(oai_file or oai_sys)}],
        })
        covered.add("OPENAI_API_KEY")

    # Other well-known keys (Telegram, etc.)
    other_keys = []
    for entry in _WELL_KNOWN_KEYS:
        k = entry["key"]
        if k not in covered:
            file_val = env_file_keys.get(k, "")
            sys_val  = os.environ.get(k, "")
            other_keys.append({"key": k,
                                "set": bool(file_val.strip()),
                                "masked": _mask_key(file_val or sys_val)})
            covered.add(k)

    # Any remaining keys in .env not yet covered
    for k, v in env_file_keys.items():
        if k in covered:
            continue
        if any(k.endswith(s) for s in ("_KEY", "_TOKEN", "_ID", "_SECRET")):
            other_keys.append({"key": k, "set": bool(v.strip()), "masked": _mask_key(v)})
            covered.add(k)

    return JSONResponse({"providers": providers, "other_keys": other_keys})

@app.post("/api/keys")
async def save_keys(request: Request):
    """Write one or more keys to .env and update the running process."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    env_file = AION_DIR / ".env"
    lines    = env_file.read_text(encoding="utf-8").splitlines() if env_file.is_file() else []

    updated  = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in body and body[k]:
                new_lines.append(f"{k}={body[k]}")
                os.environ[k] = body[k]
                updated.add(k)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    for k, v in body.items():
        if k not in updated and v:
            new_lines.append(f"{k}={v}")
            os.environ[k] = v

    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return JSONResponse({"ok": True, "updated": list(body.keys())})

# ── File Processing API ──────────────────────────────────────────────────────────

@app.post("/api/process_file")
async def process_file(request: Request):
    """Receive an uploaded file and return extracted text/transcript."""
    import tempfile
    from fastapi import UploadFile
    try:
        form     = await request.form()
        upload   = form.get("file")
        if upload is None:
            return JSONResponse({"ok": False, "error": "No file in request"}, status_code=400)
        filename = upload.filename or "unknown"
        MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
        # Größe prüfen ohne die komplette Datei in RAM zu lesen
        upload.file.seek(0, 2)
        file_size = upload.file.tell()
        upload.file.seek(0)
        if file_size > MAX_UPLOAD_BYTES:
            return JSONResponse({"ok": False, "error": "Datei zu groß (max 50 MB)"}, status_code=413)
        content  = await upload.read()
        ext      = Path(filename).suffix.lower()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Upload error: {e}"}, status_code=400)

    # ── PDF ──────────────────────────────────────────────────────────────────────
    if ext == ".pdf":
        try:
            import io
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages  = [p.extract_text() or "" for p in reader.pages]
            text   = "\n\n".join(p for p in pages if p.strip())
            return JSONResponse({"ok": True, "type": "pdf", "name": filename,
                                 "text": text[:60000], "pages": len(pages)})
        except ImportError:
            return JSONResponse({"ok": False, "error": "pypdf not installed — run: pip install pypdf"})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)})

    # ── Word ─────────────────────────────────────────────────────────────────────
    if ext in (".docx", ".doc"):
        try:
            import io, docx as _docx
            doc  = _docx.Document(io.BytesIO(content))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return JSONResponse({"ok": True, "type": "docx", "name": filename, "text": text[:60000]})
        except ImportError:
            return JSONResponse({"ok": False, "error": "python-docx not installed — run: pip install python-docx"})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)})

    # ── Excel ────────────────────────────────────────────────────────────────────
    if ext in (".xlsx", ".xls"):
        try:
            import io, openpyxl
            wb   = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            rows = []
            for sheet in wb.worksheets:
                rows.append(f"[Sheet: {sheet.title}]")
                for row in sheet.iter_rows(values_only=True):
                    rows.append("\t".join("" if c is None else str(c) for c in row))
            text = "\n".join(rows)
            return JSONResponse({"ok": True, "type": "xlsx", "name": filename, "text": text[:60000]})
        except ImportError:
            return JSONResponse({"ok": False, "error": "openpyxl not installed — run: pip install openpyxl"})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)})

    # ── Audio ────────────────────────────────────────────────────────────────────
    if ext in (".ogg", ".mp3", ".wav", ".m4a", ".flac", ".aac", ".opus", ".weba"):
        transcribe_fn = (_aion_module._plugin_tools.get("audio_transcribe_any") or {}).get("func")
        if not transcribe_fn:
            return JSONResponse({"ok": False, "error": "audio_pipeline plugin not loaded",
                                 "hint": "Load the audio_pipeline plugin to enable audio transcription"})
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            result     = transcribe_fn(file_path=tmp_path)
            transcript = result.get("text") or result.get("transcript") or ""
            if not transcript:
                return JSONResponse({"ok": False, "error": "Transcription returned empty result"})
            return JSONResponse({"ok": True, "type": "audio", "name": filename,
                                 "text": f"[Transkription: {filename}]\n{transcript}"})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)})
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    # ── CSV / plain text ─────────────────────────────────────────────────────────
    if ext in (".csv", ".tsv"):
        try:
            text = content.decode("utf-8", errors="replace")
            return JSONResponse({"ok": True, "type": "csv", "name": filename, "text": text[:60000]})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)})

    return JSONResponse({"ok": False, "error": f"No processor for {ext}"})

# ── Config API ──────────────────────────────────────────────────────────────────

@app.get("/api/providers")
async def list_providers():
    """Returns all registered LLM providers and their models.
    Wenn ein Provider eine list_models_fn registriert hat, werden die Modelle
    dynamisch von der Provider-API abgerufen (Timeout 4s, Fallback auf statische Liste)."""
    registry = getattr(_aion_module, "_provider_registry", [])

    async def _fetch_provider_models(entry: dict) -> dict:
        """Fragt Modelle eines Providers ab — parallel, mit 10s Timeout pro Provider."""
        models = list(entry.get("models", []))
        fn = entry.get("list_models_fn")
        if fn:
            try:
                dyn = await asyncio.wait_for(fn(), timeout=10.0)
                if dyn:
                    models = dyn
            except Exception:
                pass  # Fallback auf statische Liste
        return {
            "label":  entry.get("label", entry.get("prefix", "?")),
            "prefix": entry.get("prefix", ""),
            "models": models,
            "env_keys": entry.get("env_keys", []),
        }

    # Alle Provider-Abfragen parallel starten
    providers = list(await asyncio.gather(
        *[_fetch_provider_models(e) for e in registry],
        return_exceptions=False,
    ))
    # OpenAI — immer als Default-Fallback inkludieren
    # Modelle dynamisch abrufen falls OPENAI_API_KEY gesetzt, sonst statische Fallback-Liste
    _openai_static = [
        "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
        "gpt-4o", "gpt-4o-mini",
        "o4-mini", "o3", "o3-mini", "o1", "o1-mini",
        "chatgpt-4o-latest",
    ]
    _openai_models = _openai_static
    _openai_key    = _read_env_file().get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if _openai_key:
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=10.0) as _hc:
                _r = await _hc.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {_openai_key}"},
                )
                if _r.status_code == 200:
                    _prefixes = ("gpt-", "o1-", "o1", "o3-", "o3", "o4-", "chatgpt-")
                    _ids = sorted(
                        [m["id"] for m in _r.json().get("data", [])
                         if any(m.get("id", "").startswith(p) for p in _prefixes)],
                        reverse=True,
                    )
                    if _ids:
                        _openai_models = _ids
        except Exception:
            pass
    providers.append({
        "label":   "OpenAI",
        "prefix":  "",
        "models":  _openai_models,
        "default": True,
    })
    return JSONResponse({
        "providers":       providers,
        "active_model":    _aion_module.MODEL,
        "total_providers": len(providers),
    })


def _register_custom_providers():
    """Liest custom_providers aus config.json und registriert sie im Provider-Registry."""
    from openai import AsyncOpenAI
    cfg = _load_config()
    for cp in cfg.get("custom_providers", []):
        name     = cp.get("name", "Custom")
        base_url = cp.get("base_url", "").rstrip("/")
        api_env  = cp.get("api_key_env", "")
        models   = cp.get("models", [])
        prefix   = cp.get("prefix", models[0].split("/")[0] if models else name.lower())
        if not base_url or not models:
            continue
        def _make_build_fn(bu, ae):
            def _build(model):
                key = os.environ.get(ae, "") or "custom"
                return AsyncOpenAI(api_key=key, base_url=bu)
            return _build
        _aion_module.register_provider(
            prefix=prefix,
            build_fn=_make_build_fn(base_url, api_env),
            label=name,
            models=models,
            env_keys=[api_env] if api_env else [],
        )

# Custom Provider beim Start registrieren
try:
    _register_custom_providers()
except Exception as _e:
    print(f"[aion_web] Custom providers: {_e}")


@app.get("/api/custom-providers")
async def get_custom_providers():
    cfg = _load_config()
    return JSONResponse({"providers": cfg.get("custom_providers", [])})


@app.post("/api/custom-providers")
async def save_custom_provider(request: Request):
    body      = await request.json()
    name      = (body.get("name") or "").strip()
    base_url  = (body.get("base_url") or "").strip().rstrip("/")
    api_env   = (body.get("api_key_env") or "").strip().upper()
    models_raw = (body.get("models") or "")
    models    = [m.strip() for m in models_raw.split(",") if m.strip()]
    prefix    = (body.get("prefix") or "").strip()
    if not name or not base_url or not models:
        return JSONResponse({"error": "name, base_url und models sind erforderlich"}, status_code=400)
    if not prefix:
        prefix = models[0].split("/")[0] if "/" in models[0] else models[0].split("-")[0]
    cfg = _load_config()
    custom = [p for p in cfg.get("custom_providers", []) if p.get("name") != name]
    custom.append({"name": name, "base_url": base_url, "api_key_env": api_env,
                   "models": models, "prefix": prefix})
    cfg["custom_providers"] = custom
    _save_config(cfg)
    _register_custom_providers()
    return JSONResponse({"ok": True, "registered": name})


@app.delete("/api/custom-providers/{name}")
async def delete_custom_provider(name: str):
    cfg = _load_config()
    cfg["custom_providers"] = [p for p in cfg.get("custom_providers", []) if p.get("name") != name]
    _save_config(cfg)
    _register_custom_providers()
    return JSONResponse({"ok": True})


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

@app.get("/api/permissions")
async def get_permissions():
    perms  = _aion_module._load_permissions()
    preset = perms.pop("preset", None)
    cfg    = _load_config()
    saved  = cfg.get("permissions", {})
    preset = saved.get("preset", "balanced")
    return JSONResponse({
        "permissions": perms,
        "preset":      preset,
        "labels":      _aion_module.PERMISSION_LABELS,
        "defaults":    _aion_module.PERMISSION_DEFAULTS,
    })

@app.post("/api/permissions")
async def save_permissions(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    cfg = _load_config()
    existing = cfg.get("permissions", {})
    existing.update(body)
    cfg["permissions"] = existing
    _save_config(cfg)
    return JSONResponse({"ok": True, "permissions": existing})

@app.post("/api/config/reset_exchanges")
async def reset_exchanges():
    cfg = _load_config()
    cfg["exchange_count"] = 0
    _save_config(cfg)
    _session.exchange_count = 0
    return JSONResponse({"ok": True})

@app.post("/api/config/settings")
async def save_settings(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    cfg     = _load_config()
    allowed = {
        "tts_engine", "tts_voice", "model_fallback", "browser_headless", "task_routing",
        "thinking_level", "thinking_overrides", "channel_allowlist",
        "check_model", "max_history_turns",
    }
    for k, v in body.items():
        if k in allowed:
            cfg[k] = v
    _save_config(cfg)
    return JSONResponse({"ok": True})

# ── Thinking Level ──────────────────────────────────────────────────────────────

@app.get("/api/config/thinking")
async def get_thinking():
    cfg = _load_config()
    return JSONResponse({
        "thinking_level":    cfg.get("thinking_level", "standard"),
        "thinking_overrides": cfg.get("thinking_overrides", {}),
    })

@app.post("/api/config/thinking")
async def save_thinking(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    level   = body.get("level", "").strip().lower()
    channel = body.get("channel", "").strip()
    valid   = {"minimal", "standard", "deep", "ultra"}
    if level and level not in valid:
        return JSONResponse({"error": f"Ungültiger Level. Erlaubt: {', '.join(sorted(valid))}"}, status_code=400)
    cfg = _load_config()
    if channel:
        if "thinking_overrides" not in cfg:
            cfg["thinking_overrides"] = {}
        if level:
            cfg["thinking_overrides"][channel] = level
        else:
            cfg["thinking_overrides"].pop(channel, None)
    elif level:
        cfg["thinking_level"] = level
    _save_config(cfg)
    return JSONResponse({
        "ok": True,
        "thinking_level":     cfg.get("thinking_level", "standard"),
        "thinking_overrides": cfg.get("thinking_overrides", {}),
    })

# ── Channel Allowlist ────────────────────────────────────────────────────────────

@app.get("/api/config/allowlist")
async def get_allowlist():
    cfg = _load_config()
    return JSONResponse({"channel_allowlist": cfg.get("channel_allowlist", [])})

@app.post("/api/config/allowlist")
async def save_allowlist(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    channels = body.get("channels", None)
    if channels is None:
        return JSONResponse({"error": "'channels' fehlt"}, status_code=400)
    if not isinstance(channels, list):
        return JSONResponse({"error": "'channels' muss eine Liste sein"}, status_code=400)
    cfg = _load_config()
    cfg["channel_allowlist"] = [str(c).strip() for c in channels if str(c).strip()]
    _save_config(cfg)
    return JSONResponse({"ok": True, "channel_allowlist": cfg["channel_allowlist"]})

# ── Audio File Serving ──────────────────────────────────────────────────────────

@app.get("/api/audio/{filename}")
async def serve_audio(filename: str):
    """Serviert eine Temp-Audiodatei (erzeugt von audio_tts) für den Web UI Player."""
    import tempfile
    from fastapi.responses import FileResponse
    # Sicherheit: nur erlaubte Endungen, kein Path-Traversal
    allowed_ext = {".mp3", ".wav", ".ogg", ".m4a", ".opus"}
    p = Path(filename)
    if p.suffix.lower() not in allowed_ext or "/" in filename or "\\" in filename or ".." in filename:
        return JSONResponse({"error": "invalid filename"}, status_code=400)
    audio_path = Path(tempfile.gettempdir()) / filename
    if not audio_path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    mime_map = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
                ".m4a": "audio/mp4", ".opus": "audio/opus"}
    mime = mime_map.get(p.suffix.lower(), "audio/mpeg")
    return FileResponse(str(audio_path), media_type=mime)

def _find_claude_bin_web():
    """Hilfsfunktion: sucht claude CLI (wiederverwendet in mehreren Endpoints)."""
    import shutil, glob as _glob
    found = shutil.which("claude")
    if found:
        return found
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        candidates = [
            os.path.join(os.environ.get("APPDATA", ""), "npm", "claude.cmd"),
            os.path.join(os.environ.get("APPDATA", ""), "npm", "claude"),
            os.path.join(home, ".claude", "local", "claude.exe"),
            *_glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""),
                "Microsoft", "WinGet", "Packages", "Anthropic.Claude*", "**", "claude.exe"),
                recursive=True),
        ]
    else:
        # macOS / Linux: npm global bin + common prefix paths
        candidates = [
            os.path.join(home, ".npm-global", "bin", "claude"),
            os.path.join(home, ".local", "bin", "claude"),
            "/usr/local/bin/claude",
            "/usr/bin/claude",
            os.path.join(home, ".claude", "local", "claude"),
        ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None

@app.get("/api/claude-cli/status")
async def claude_cli_status():
    """Prüft ob claude CLI installiert und authentifiziert ist."""
    import subprocess
    bin_path = _find_claude_bin_web()
    if not bin_path:
        return JSONResponse({"installed": False, "authenticated": False, "path": None})
    try:
        r = subprocess.run(
            [bin_path, "--print", "--model", "claude-haiku-4-5-20251001", "ping"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        authed = r.returncode == 0
    except Exception:
        authed = False
    return JSONResponse({"installed": True, "authenticated": authed, "path": bin_path})

_claude_login_proc = None  # laufender login-Prozess

@app.post("/api/claude-cli/login")
async def claude_cli_login():
    """Startet 'claude login' — öffnet den Browser für die Anmeldung."""
    import subprocess
    global _claude_login_proc

    bin_path = _find_claude_bin_web()
    if not bin_path:
        # Claude CLI nicht installiert → erst installieren via npm
        import shutil
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            return JSONResponse({
                "ok": False,
                "step": "no_npm",
                "error": "npm nicht gefunden. Node.js installieren: https://nodejs.org",
            })
        # npm install in Background-Task
        try:
            r = subprocess.run(
                [npm, "install", "-g", "@anthropic-ai/claude-code"],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0:
                return JSONResponse({"ok": False, "step": "install_failed", "error": r.stderr[:300]})
            bin_path = _find_claude_bin_web()
            if not bin_path:
                return JSONResponse({"ok": False, "step": "install_failed",
                                     "error": "Nach Installation nicht gefunden — Terminal neu starten."})
        except Exception as e:
            return JSONResponse({"ok": False, "step": "install_failed", "error": str(e)})

    # Bereits angemeldet?
    try:
        chk = subprocess.run(
            [bin_path, "--print", "--model", "claude-haiku-4-5-20251001", "ping"],
            capture_output=True, text=True, timeout=8, encoding="utf-8", errors="replace",
        )
        if chk.returncode == 0:
            return JSONResponse({"ok": True, "step": "already_authenticated",
                                 "message": "Bereits angemeldet."})
    except Exception:
        pass

    # Login starten (öffnet Browser)
    try:
        if sys.platform == "win32":
            _claude_login_proc = subprocess.Popen(
                [bin_path, "login"],
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            _claude_login_proc = subprocess.Popen([bin_path, "login"])
        return JSONResponse({
            "ok": True,
            "step": "browser_opened",
            "message": "Browser wurde geöffnet. Melde dich mit deinem Claude-Konto an — danach 'Status prüfen' klicken.",
        })
    except Exception as e:
        return JSONResponse({"ok": False, "step": "launch_failed", "error": str(e)})

# ── Google OAuth ───────────────────────────────────────────────────────────────
_GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_SCOPE     = "https://www.googleapis.com/auth/generative-language"
_OAUTH_STATE: dict = {}

@app.get("/api/oauth/google/start")
async def google_oauth_start():
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        return JSONResponse({"error": "GOOGLE_CLIENT_ID nicht gesetzt"}, status_code=400)
    import secrets, time
    state = secrets.token_urlsafe(16)
    _OAUTH_STATE["state"] = state
    _OAUTH_STATE["created"] = time.time()  # Ablaufzeit: 5 Minuten
    redirect_uri = "http://localhost:7000/api/oauth/google/callback"
    url = (
        f"{_GOOGLE_AUTH_URL}?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={_GOOGLE_SCOPE}"
        f"&state={state}"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return JSONResponse({"url": url})

@app.get("/api/oauth/google/callback")
async def google_oauth_callback(code: str = "", state: str = "", error: str = ""):
    close_script = "<script>setTimeout(()=>{window.opener?.postMessage(%s,'*');window.close()},200);</script>"
    if error:
        _err_json = '{"error":"' + error + '"}'
        return HTMLResponse(f"<html><body>{close_script % repr(_err_json)}Fehler: {error}</body></html>")
    import time as _time
    if state != _OAUTH_STATE.get("state"):
        _state_json = '{"error":"invalid_state"}'
        return HTMLResponse(f"<html><body>{close_script % repr(_state_json)}Ungültiger State</body></html>")
    if _time.time() - _OAUTH_STATE.get("created", 0) > 300:  # 5 Minuten Ablauf
        _OAUTH_STATE.clear()
        _exp_json = '{"error":"state_expired"}'
        return HTMLResponse(f"<html><body>{close_script % repr(_exp_json)}OAuth-State abgelaufen — bitte erneut starten</body></html>")
    _OAUTH_STATE.clear()  # State nach Nutzung invalidieren (CSRF-Schutz)
    client_id     = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    redirect_uri  = "http://localhost:7000/api/oauth/google/callback"
    import httpx
    async with httpx.AsyncClient() as hc:
        r = await hc.post(_GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     client_id,
            "client_secret": client_secret,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        })
    if r.status_code != 200:
        _token_json = '{"error":"token_failed"}'
        return HTMLResponse(f"<html><body>{close_script % repr(_token_json)}Token-Fehler: {r.text}</body></html>")
    tokens        = r.json()
    refresh_token = tokens.get("refresh_token", "")
    if refresh_token:
        env_file  = AION_DIR / ".env"
        lines     = env_file.read_text(encoding="utf-8").splitlines() if env_file.is_file() else []
        new_lines = []
        updated   = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("GOOGLE_REFRESH_TOKEN="):
                new_lines.append(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
        env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        os.environ["GOOGLE_REFRESH_TOKEN"] = refresh_token
    return HTMLResponse("<html><body><script>setTimeout(()=>{window.opener?.postMessage({ok:true},'*');window.close()},200);</script><p style='font-family:monospace;padding:20px'>✓ Erfolgreich verbunden</p></body></html>")

if __name__ == "__main__":
    # Hinweis wenn noch kein API-Key konfiguriert — kein harter Abbruch, da der User
    # den Key auch direkt im Web UI (Settings → API Keys) hinterlegen kann.
    _env_keys = _read_env_file()
    _has_key  = bool(_env_keys.get("OPENAI_API_KEY", "").strip()) or \
                bool(_env_keys.get("GEMINI_API_KEY", "").strip())
    if not _has_key:
        print("[AION] Hinweis: Noch kein API-Key in .env hinterlegt.")
        print("[AION] Bitte im Web UI unter Settings → API Keys konfigurieren.")
        print("[AION] Alternativ: 'aion --setup' ausführen.")
    _port = int(os.environ.get("AION_PORT", 7000))
    _host = os.environ.get("AION_HOST", "127.0.0.1")
    print(f"Starte AION Web UI auf http://{_host}:{_port}")
    print(f"Modell: {_aion_module.MODEL}")
    if _host != "127.0.0.1":
        print(f"Hinweis: Server erreichbar im Netzwerk (AION_HOST={_host}) — kein Passwortschutz aktiv.")
    print("Beenden: Strg+C\n")
    uvicorn.run(app, host=_host, port=_port, log_level="warning")
