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
    try:
        async for event in _session.stream(user_input, images=images):
            yield _sse(event)
    except Exception as e:
        yield _sse({"type": "error", "text": f"[AION Fehler] {e}"})

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

@app.get("/api/keys")
async def get_keys():
    """Returns all known API keys (masked) grouped by provider."""
    registry  = getattr(_aion_module, "_provider_registry", [])
    covered   = set()
    providers = []

    for entry in registry:
        env_keys = entry.get("env_keys", [])
        if not env_keys:
            continue
        keys_info = []
        for k in env_keys:
            val = os.environ.get(k, "")
            keys_info.append({"key": k, "set": bool(val), "masked": _mask_key(val)})
            covered.add(k)
        providers.append({
            "label":    entry.get("label", entry.get("prefix", "?")),
            "env_keys": keys_info,
        })

    # OpenAI fallback (not in registry, always shown)
    oai_val = os.environ.get("OPENAI_API_KEY", "")
    if "OPENAI_API_KEY" not in covered:
        providers.append({
            "label":    "OpenAI",
            "env_keys": [{"key": "OPENAI_API_KEY", "set": bool(oai_val), "masked": _mask_key(oai_val)}],
        })
        covered.add("OPENAI_API_KEY")

    # Other well-known keys (Telegram, etc.)
    other_keys = []
    for entry in _WELL_KNOWN_KEYS:
        k = entry["key"]
        if k not in covered:
            val = os.environ.get(k, "")
            other_keys.append({"key": k, "set": bool(val), "masked": _mask_key(val)})
            covered.add(k)

    # Any remaining keys in .env not yet covered
    env_file = AION_DIR / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k = line.split("=", 1)[0].strip()
            if k in covered:
                continue
            if any(k.endswith(s) for s in ("_KEY", "_TOKEN", "_ID", "_SECRET")):
                val = os.environ.get(k, "")
                other_keys.append({"key": k, "set": bool(val), "masked": _mask_key(val)})
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
    """Returns all registered LLM providers and their known models."""
    registry = getattr(_aion_module, "_provider_registry", [])
    providers = []
    for entry in registry:
        providers.append({
            "label":  entry.get("label", entry.get("prefix", "?")),
            "prefix": entry.get("prefix", ""),
            "models": entry.get("models", []),
        })
    # Always include OpenAI as the default fallback
    providers.append({
        "label":  "OpenAI",
        "prefix": "",
        "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini", "o3", "o4-mini"],
        "default": True,
    })
    return JSONResponse({
        "providers":      providers,
        "active_model":   _aion_module.MODEL,
        "total_providers": len(providers),
    })


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
    allowed = {"tts_engine", "tts_voice", "model_fallback", "browser_headless"}
    for k, v in body.items():
        if k in allowed:
            cfg[k] = v
    _save_config(cfg)
    return JSONResponse({"ok": True})

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
    import secrets
    state = secrets.token_urlsafe(16)
    _OAUTH_STATE["state"] = state
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
        return HTMLResponse(f"<html><body>{close_script % repr('{\"error\":\"'+error+'\"}')}Fehler: {error}</body></html>")
    if state != _OAUTH_STATE.get("state"):
        return HTMLResponse(f"<html><body>{close_script % repr('{\"error\":\"invalid_state\"}')}Ungültiger State</body></html>")
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
        return HTMLResponse(f"<html><body>{close_script % repr('{\"error\":\"token_failed\"}')}Token-Fehler: {r.text}</body></html>")
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
    has_key = bool(os.environ.get("OPENAI_API_KEY", "").strip()) or \
              bool(os.environ.get("GEMINI_API_KEY", "").strip())
    if not has_key:
        print("Fehler: Kein API-Key gesetzt (OPENAI_API_KEY oder GEMINI_API_KEY fehlt).")
        sys.exit(1)
    _port = int(os.environ.get("AION_PORT", 7000))
    _host = os.environ.get("AION_HOST", "127.0.0.1")
    print(f"Starte AION Web UI auf http://{_host}:{_port}")
    print(f"Modell: {_aion_module.MODEL}")
    if _host != "127.0.0.1":
        print(f"Hinweis: Server erreichbar im Netzwerk (AION_HOST={_host}) — kein Passwortschutz aktiv.")
    print("Beenden: Strg+C\n")
    uvicorn.run(app, host=_host, port=_port, log_level="warning")
