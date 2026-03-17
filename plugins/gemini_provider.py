"""
AION Plugin: Gemini Provider (google-genai SDK) mit Function Calling
=====================================================================
Nutzt das offizielle Google Gen AI SDK mit echtem Function Calling.

Installation:
  pip install google-genai
  GEMINI_API_KEY=AIza... in .env setzen
"""

import asyncio
import json
import os
import aion as _aion_module

GEMINI_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
]


def _is_gemini(model: str) -> bool:
    return model.startswith("gemini")


def _openai_schema_to_gemini(openai_tools: list) -> list:
    """Konvertiert OpenAI Tool-Schemas in Gemini FunctionDeclaration-Format."""
    from google.genai import types as t

    def clean_schema(s):
        """Bereinigt Schema: entfernt title-Felder, gibt None zurück wenn leer."""
        if not isinstance(s, dict):
            return s
        return {k: clean_schema(v) for k, v in s.items() if k != "title"}

    declarations = []
    for tool in openai_tools:
        fn = tool.get("function", {})
        name = fn.get("name", "")
        desc = fn.get("description", "")
        params = fn.get("parameters", {})

        # Gemini erlaubt properties/required NUR bei type=object mit echten properties
        has_properties = (
            isinstance(params, dict)
            and params.get("type") == "object"
            and bool(params.get("properties"))
        )

        declarations.append(
            t.FunctionDeclaration(
                name=name,
                description=desc,
                parameters=clean_schema(params) if has_properties else None,
            )
        )
    return declarations


def _make_chunk(text=None, tool_calls=None):
    """Erstellt ein OpenAI-ähnliches Streaming-Chunk-Objekt."""

    class FunctionCall:
        def __init__(self, index, id_, name, arguments):
            self.index = index
            self.id = id_
            self.function = type("F", (), {"name": name, "arguments": arguments})()

    class Delta:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []

    class Choice:
        def __init__(self, delta):
            self.delta = delta
            self.finish_reason = None

    class Chunk:
        def __init__(self, text=None, tool_calls=None):
            tcs = None
            if tool_calls:
                tcs = [
                    FunctionCall(i, tc["id"], tc["name"], tc["arguments"])
                    for i, tc in enumerate(tool_calls)
                ]
            self.choices = [Choice(Delta(content=text, tool_calls=tcs))]

    return Chunk(text=text, tool_calls=tool_calls)


class _GeminiStreamIterator:
    """Liefert OpenAI-kompatible Chunks aus einer Gemini-Antwort."""

    def __init__(self, text: str, tool_calls: list):
        self._chunks = []

        if tool_calls:
            self._chunks.append(_make_chunk(tool_calls=tool_calls))
        elif text:
            size = 50
            for i in range(0, len(text), size):
                self._chunks.append(_make_chunk(text=text[i:i+size]))

        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._idx]
        self._idx += 1
        return chunk


class _GeminyChatCompletions:
    def __init__(self, model: str):
        self._model = model

    def _get_client(self):
        try:
            from google import genai
            return genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
        except ImportError:
            raise RuntimeError("google-genai nicht installiert: pip install google-genai")

    def _build_contents(self, messages: list):
        """Konvertiert OpenAI-Messages in Gemini Contents."""
        from google.genai import types as t

        system_instruction = None
        contents = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content") or ""

            if role == "system":
                system_instruction = content
                continue

            if role == "tool":
                try:
                    result_data = json.loads(content)
                except Exception:
                    result_data = {"result": str(content)}
                fn_name = "tool_result"
                contents.append(t.Content(
                    role="user",
                    parts=[t.Part.from_function_response(
                        name=fn_name,
                        response=result_data,
                    )]
                ))
                continue

            if role == "assistant":
                parts = []
                if content:
                    parts.append(t.Part.from_text(text=content))
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except Exception:
                        args = {}
                    parts.append(t.Part.from_function_call(
                        name=fn.get("name", ""),
                        args=args,
                    ))
                if parts:
                    contents.append(t.Content(role="model", parts=parts))
                continue

            # User-Message
            if isinstance(content, list):
                parts = [t.Part.from_text(text=c.get("text", ""))
                         for c in content if isinstance(c, dict)]
            else:
                parts = [t.Part.from_text(text=content)] if content else []

            if parts:
                contents.append(t.Content(role="user", parts=parts))

        return system_instruction, contents

    async def create(self, model, messages, tools=None, tool_choice=None,
                     max_tokens=4096, temperature=0.7, stream=False, **kwargs):
        from google.genai import types as t

        client = self._get_client()
        system_instruction, contents = self._build_contents(messages)

        config_kwargs = {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        # Function Calling — tools in config eintragen
        if tools:
            declarations = _openai_schema_to_gemini(tools)
            if declarations:
                config_kwargs["tools"] = [t.Tool(function_declarations=declarations)]
                config_kwargs["tool_config"] = t.ToolConfig(
                    function_calling_config=t.FunctionCallingConfig(mode="AUTO")
                )

        config = t.GenerateContentConfig(**config_kwargs)

        # Synchronen SDK-Call in Thread ausführen (SDK ist nicht async)
        def _call():
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

        response = await asyncio.get_event_loop().run_in_executor(None, _call)

        # Antwort parsen — Text oder Tool-Calls
        text_out = ""
        tool_calls_out = []

        for candidate in response.candidates or []:
            for part in (candidate.content.parts if candidate.content else []):
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls_out.append({
                        "id":        f"call_{fc.name}_{len(tool_calls_out)}",
                        "name":      fc.name,
                        "arguments": json.dumps(dict(fc.args) if fc.args else {}),
                    })
                elif hasattr(part, "text") and part.text:
                    text_out += part.text

        return _GeminiStreamIterator(text=text_out, tool_calls=tool_calls_out)


class _GeminiAdapter:
    """OpenAI-kompatibler Client-Wrapper für Gemini."""

    def __init__(self, model: str):
        self.model = model
        self.chat = type("Chat", (), {
            "completions": _GeminyChatCompletions(model)
        })()


def _detect_provider(model: str) -> str:
    return "gemini" if _is_gemini(model) else "openai"


def _build_client(model: str):
    if _is_gemini(model):
        return _GeminiAdapter(model)
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


def _switch_model(params: dict) -> dict:
    model = params.get("model", "").strip()
    if not model:
        return {"error": "Kein Modell angegeben."}
    _aion_module.MODEL = model
    _aion_module.client = _build_client(model)
    return {"ok": True, "model": model, "provider": _detect_provider(model)}


def register(api):
    _aion_module._build_client    = _build_client
    _aion_module._detect_provider = _detect_provider

    current_model = _aion_module.MODEL
    if _is_gemini(current_model):
        _aion_module.client = _GeminiAdapter(current_model)

    api.register_tool(
        name="switch_model",
        description=(
            "Wechselt das aktive KI-Modell. "
            "OpenAI: gpt-4.1, gpt-4.1-mini, gpt-4o, gpt-4o-mini, o3, o4-mini. "
            "Gemini: gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite, "
            "gemini-2.0-flash, gemini-2.0-flash-lite, gemini-1.5-pro."
        ),
        func=_switch_model,
        input_schema={
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Modellname"}
            },
            "required": ["model"],
        },
    )
    print(f"[Plugin] gemini_provider geladen (Function Calling aktiv) — {len(GEMINI_MODELS)} Modelle")
