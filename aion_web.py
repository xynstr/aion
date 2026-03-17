"""
AION Web UI — FastAPI + SSE Live-Stream
Starten:
  pip install fastapi uvicorn
  set OPENAI_API_KEY=sk-...
  python aion_web.py
Öffnen: http://localhost:7000
"""

import asyncio
import json
import os
import sys
import time
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
from aion import (
    memory,
    _dispatch,
    _build_tool_schemas,
    _build_system_prompt,
    _load_character,
    CHARACTER_FILE,
    BOT_DIR,
    MAX_TOOL_ITERATIONS,
)

# ── Config-Datei für persistente Einstellungen ────────────────────────────────

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
    # _build_client vom Plugin nutzen falls vorhanden, sonst Standard-OpenAI
    if hasattr(_aion_module, "_build_client"):
        _aion_module.client = _aion_module._build_client(model)
    else:
        from openai import AsyncOpenAI
        _aion_module.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

_startup_model = _get_model()

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Konfiguriertes Modell aus config.json anwenden (nach Plugin-Load)."""
    m = _startup_model
    _aion_module.MODEL = m
    if hasattr(_aion_module, "_build_client"):
        _aion_module.client = _aion_module._build_client(m)
    print(f"[AION] Startup-Modell: {m}")
    yield

app = FastAPI(title="AION", lifespan=_lifespan)

_conversation: list[dict] = []

# ── SSE-Helper ────────────────────────────────────────────────────────────────

def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"

# ── Streaming Chat-Loop ───────────────────────────────────────────────────────

async def _stream_chat(user_input: str) -> AsyncGenerator[str, None]:
    global _conversation

    mem_ctx          = memory.get_context(user_input)
    system_prompt    = _build_system_prompt()
    effective_system = system_prompt + ("\n\n" + mem_ctx if mem_ctx else "")
    messages         = _conversation + [{"role": "user", "content": user_input}]
    final_text       = ""
    current_model    = _aion_module.MODEL
    client           = _aion_module.client

    try:
        for _iter in range(MAX_TOOL_ITERATIONS):
            tools  = _build_tool_schemas()
            stream = await client.chat.completions.create(
                model=current_model,
                messages=[{"role": "system", "content": effective_system}] + messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=4096,
                temperature=0.7,
                stream=True,
            )

            text_content    = ""
            tool_calls_acc: dict[int, dict] = {}

            async for chunk in stream:
                choice = chunk.choices[0]
                delta  = choice.delta

                if delta.content:
                    text_content += delta.content
                    yield _sse("token", {"content": delta.content})

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "args_str": ""}
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["args_str"] += tc.function.arguments

            if tool_calls_acc:
                tc_list = [
                    {
                        "id": tool_calls_acc[i]["id"],
                        "type": "function",
                        "function": {
                            "name":      tool_calls_acc[i]["name"],
                            "arguments": tool_calls_acc[i]["args_str"],
                        },
                    }
                    for i in sorted(tool_calls_acc)
                ]
                asst_msg: dict = {"role": "assistant", "tool_calls": tc_list}
                if text_content:
                    asst_msg["content"] = text_content
                messages.append(asst_msg)

                tool_results = []
                for i in sorted(tool_calls_acc):
                    tc      = tool_calls_acc[i]
                    fn_name = tc["name"]
                    try:
                        fn_inputs = json.loads(tc["args_str"] or "{}")
                    except Exception:
                        fn_inputs = {}

                    # "reflect"-Tool: Gedanke sofort als thought-Event streamen
                    if fn_name == "reflect":
                        thought_text = fn_inputs.get("thought", "")
                        trigger      = fn_inputs.get("trigger", "allgemein")
                        if thought_text:
                            yield _sse("thought", {
                                "text":    thought_text,
                                "trigger": trigger,
                                "call_id": tc["id"],
                            })

                    yield _sse("tool_call", {
                        "tool":    fn_name,
                        "args":    fn_inputs,
                        "call_id": tc["id"],
                    })

                    t0         = time.monotonic()
                    result_raw = await _dispatch(fn_name, fn_inputs)
                    duration   = round(time.monotonic() - t0, 2)

                    try:
                        result_data = json.loads(result_raw)
                    except Exception:
                        result_data = {"raw": str(result_raw)}

                    ok = "error" not in result_data

                    yield _sse("tool_result", {
                        "tool":     fn_name,
                        "call_id":  tc["id"],
                        "result":   result_data,
                        "ok":       ok,
                        "duration": duration,
                    })

                    tool_results.append({
                        "role":         "tool",
                        "tool_call_id": tc["id"],
                        "content":      result_raw,
                    })

                messages.extend(tool_results)

            else:
                final_text = text_content
                messages.append({"role": "assistant", "content": final_text})
                break

        _conversation = messages

        # Auto-Memory
        if final_text:
            try:
                last_user = next(
                    (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
                )
                memory.record(
                    category="conversation",
                    summary=last_user[:120],
                    lesson=f"Nutzer: '{last_user[:200]}' → AION: '{final_text[:300]}'",
                    success=True,
                )
            except Exception:
                pass

        yield _sse("done", {"full_response": final_text})

    except Exception as exc:
        yield _sse("error", {"message": str(exc)})

# ── API-Routen ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    p = AION_DIR / "static" / "index.html"
    if p.is_file():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>index.html nicht gefunden</h1>", status_code=404)

@app.post("/api/chat")
async def chat(request: Request):
    body       = await request.json()
    user_input = body.get("message", "").strip()
    if not user_input:
        return JSONResponse({"error": "Leere Nachricht"}, status_code=400)
    return StreamingResponse(
        _stream_chat(user_input),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )

@app.post("/api/reset")
async def reset():
    global _conversation
    _conversation = []
    return JSONResponse({"ok": True})

@app.get("/api/status")
async def status():
    return JSONResponse({
        "model":           _aion_module.MODEL,
        "memory_entries":  len(memory._entries),
        "conversation_len": len(_conversation),
        "character":       _load_character()[:500],
    })

@app.post("/api/model")
async def set_model(request: Request):
    body  = await request.json()
    model = body.get("model", "").strip()
    if not model:
        return JSONResponse({"error": "Kein Modell angegeben"}, status_code=400)
    _set_model(model)
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
