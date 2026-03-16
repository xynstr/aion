"""
AION Web UI — FastAPI + SSE Live-Gedanken

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
from pathlib import Path
from typing import AsyncGenerator

AION_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(AION_DIR))

# Lade .env Umgebungsvariablen
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

from aion import (
    memory,
    _dispatch,
    _build_tool_schemas,
    MODEL,
    SYSTEM_PROMPT,
    client,
    MAX_TOOL_ITERATIONS,
)

app = FastAPI(title="AION")

# Einzelne globale Konversation (Single-User-Bot)
_conversation: list[dict] = []


# ── SSE-Helper ────────────────────────────────────────────────────────────────

def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"


# ── Streaming Chat-Loop ───────────────────────────────────────────────────────

async def _stream_chat(user_input: str) -> AsyncGenerator[str, None]:
    """
    Führt eine vollständige Konversations-Runde durch und streamt Events:
      - tool_call   → Tool wird aufgerufen (name, args, call_id)
      - tool_result → Tool hat geantwortet (result, ok, duration)
      - token       → Text-Token der Antwort
      - done        → Abgeschlossen
      - error       → Fehler
    """
    global _conversation

    mem_ctx = memory.get_context(user_input)
    effective_system = SYSTEM_PROMPT + ("\n\n" + mem_ctx if mem_ctx else "")
    messages = _conversation + [{"role": "user", "content": user_input}]
    final_text = ""

    try:
        for _iter in range(MAX_TOOL_ITERATIONS):
            # Tool-Schemas jedes Mal neu aufbauen (neue Tools könnten erstellt worden sein)
            tools = _build_tool_schemas()

            stream = await client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": effective_system}] + messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=4096,
                temperature=0.7,
                stream=True,
            )

            # Stream akkumulieren
            text_content = ""
            tool_calls_acc: dict[int, dict] = {}   # index → {id, name, args_str}

            async for chunk in stream:
                choice = chunk.choices[0]
                delta  = choice.delta

                # Text-Token → sofort streamen
                if delta.content:
                    text_content += delta.content
                    yield _sse("token", {"content": delta.content})

                # Tool-Call-Chunks akkumulieren
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

            # ── Tool-Calls vorhanden → ausführen ─────────────────────────────
            if tool_calls_acc:
                # Assistant-Nachricht mit Tool-Calls rekonstruieren
                tc_list = [
                    {
                        "id":   tool_calls_acc[i]["id"],
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

                # Jedes Tool aufrufen und Events streamen
                tool_results = []
                for i in sorted(tool_calls_acc):
                    tc      = tool_calls_acc[i]
                    fn_name = tc["name"]
                    try:
                        fn_inputs = json.loads(tc["args_str"] or "{}")
                    except Exception:
                        fn_inputs = {}

                    # Event: Tool wird aufgerufen
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

                    # Event: Tool-Ergebnis
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
                # Nächste Iteration

            # ── Keine Tool-Calls → finale Antwort ────────────────────────────
            else:
                final_text = text_content
                messages.append({"role": "assistant", "content": final_text})
                break

        # Konversation global speichern
        _conversation = messages
        yield _sse("done", {"full_response": final_text})

    except Exception as exc:
        yield _sse("error", {"message": str(exc)})


# ── API-Routen ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    p = AION_DIR / "static" / "index.html"
    if p.is_file():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>static/index.html nicht gefunden</h1>", status_code=500)


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    msg  = (body.get("message") or "").strip()
    if not msg:
        return JSONResponse({"error": "Keine Nachricht"}, status_code=400)
    return StreamingResponse(
        _stream_chat(msg),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/reset")
async def reset_conversation():
    global _conversation
    _conversation = []
    return JSONResponse({"ok": True})


@app.get("/api/status")
async def status():
    return JSONResponse({
        "model":          MODEL,
        "memory_entries": len(memory._entries),
        "conv_messages":  len(_conversation),
    })


# ── Start ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Fehler: OPENAI_API_KEY nicht gesetzt.")
        print("Setze ihn mit:  set OPENAI_API_KEY=sk-...")
        sys.exit(1)

    port = int(os.environ.get("AION_PORT", 7000))
    (AION_DIR / "static").mkdir(exist_ok=True)

    print(f"\nAION Web UI läuft → http://localhost:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
