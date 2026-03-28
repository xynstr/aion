"""
aion_session.py — AionSession Klasse (extrahiert aus aion.py)

Verwendet deferred imports von aion (import aion as _m innerhalb von Methoden)
um circular imports zu vermeiden. Python cached Module in sys.modules → O(1).
Wird von aion.py importiert: from aion_session import AionSession, run_aion_turn
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone

UTC = timezone.utc


class AionSession:
    """Eine Konversations-Sitzung auf einem Kanal (web, telegram_<id>, discord_<id>, ...).

    Alle Plattformen (Web UI, Telegram, Discord, CLI, REST API, ...) nutzen
    dieselbe Session-Klasse und bekommen damit identische Features:
      - Eigener Konversations-Kontext pro Kanal
      - Memory-Injection, Thoughts-Injection
      - Auto-Save in Tier 2 + Tier 3
      - Automatischer Charakter-Update alle 5 Gespräche

    Plattform-Adapter sind damit dünne Wrapper:
      Web UI  → session.stream(input)  → SSE-Tokens an Browser
      Telegram → session.turn(input)   → fertige Antwort als String
      Discord → session.turn(input)   → fertiger String
    """

    def __init__(self, channel: str = "default"):
        import aion as _m
        self.channel         = channel
        self.messages: list[dict] = []
        # exchange_count aus config laden damit er Neustarts überlebt
        self.exchange_count: int  = int(_m._load_config().get("exchange_count", 0))
        self._client               = None  # lazy init, gebunden an Event-Loop des Erstellers
        self._last_response_blocks = []  # Letzte response_blocks (mit Bildern) für Bots wie Telegram
        # Schedule startup compression check (once per process, in background)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_m._startup_compress_check())
        except RuntimeError:
            pass  # No running loop in this thread — skip

    def _get_client(self):
        """Gibt den Session-Client zurück; erstellt ihn beim ersten Aufruf im aktuellen Loop."""
        if self._client is None:
            import aion as _m
            self._client = _m._build_client(_m.MODEL)
        return self._client

    async def load_history(self, num_entries: int = 20, channel_filter: str = ""):
        """Lädt vergangene Nachrichten aus Tier 2 (conversation_history.jsonl) in den Kontext.

        channel_filter: wenn gesetzt, nur Einträge dieses Kanals laden.
        """
        import aion as _m
        try:
            params = {"num_entries": num_entries}
            if channel_filter:
                params["channel_filter"] = channel_filter
            raw    = await _m._dispatch("memory_read_history", params)
            result = json.loads(raw)
            if result.get("ok") and result.get("entries"):
                self.messages = result["entries"]
                print(f"[AION:{self.channel}] {len(self.messages)} Nachrichten aus History geladen.")
            else:
                print(f"[AION:{self.channel}] Noch keine frühere Konversationshistorie.")
        except Exception as e:
            print(f"[AION:{self.channel}] History-Load Fehler: {e}")

    async def stream(self, user_input: str, images: list | None = None, cancel_event: "asyncio.Event | None" = None):
        """Async-Generator: liefert Event-Dicts für jeden Verarbeitungsschritt.

        images: optionale Liste von Base64-Data-URLs (z.B. "data:image/jpeg;base64,...")
                oder öffentlichen Bild-URLs. Wenn angegeben, wird der User-Message-Content
                als multimodales Array formatiert (OpenAI Vision / Gemini).

        Event-Typen:
          {"type": "token",       "content": "..."}
          {"type": "thought",     "text": "...", "trigger": "...", "call_id": "..."}
          {"type": "tool_call",   "tool": "...", "args": {...},    "call_id": "..."}
          {"type": "tool_result", "tool": "...", "result": {...},  "ok": bool, "duration": 0.1, "call_id": "..."}
          {"type": "done",        "full_response": "..."}
          {"type": "error",       "message": "..."}
        """
        import aion as _m

        # ── Channel-Allowlist-Prüfung ──────────────────────────────────────────
        allowed, msg = _m._check_channel_allowlist(self.channel)
        if not allowed:
            yield {"type": "error", "message": msg}
            return

        mem_ctx      = await _m.memory.get_context_semantic(user_input)
        thoughts_ctx = _m._get_recent_thoughts(5)
        sys_prompt   = _m._build_system_prompt(self.channel)  # Channel-spezifisches Thinking-Prompt
        effective    = (
            sys_prompt
            + ("\n\n" + mem_ctx      if mem_ctx      else "")
            + ("\n\n" + thoughts_ctx if thoughts_ctx else "")
        )
        # Multimodaler User-Message-Content wenn Bilder vorhanden
        if images:
            user_content: list = [{"type": "text", "text": user_input or "Was siehst du auf diesem Bild?"}]
            for img in images:
                user_content.append({"type": "image_url", "image_url": {"url": img}})
            user_msg = {"role": "user", "content": user_content}
        else:
            user_msg = {"role": "user", "content": user_input}
        # History-Truncation: älteste Nachrichten kürzen um Token-Kosten zu begrenzen.
        # Limit aus config.json ("max_history_turns") oder Konstante MAX_HISTORY_TURNS.
        # Wichtig: Tool-Messages immer zusammen mit ihrem assistant-Tool-Call-Message
        # behalten — sonst API-Fehler "dangling tool_call". Daher runden wir auf Paare.
        _max_hist = int(_m._load_config().get("max_history_turns", _m.MAX_HISTORY_TURNS))
        _hist = self.messages
        if len(_hist) > _max_hist:
            # Vom Ende behalten: neueste _max_hist Nachrichten
            # Ersten user-Message als Ankerpunkt suchen damit kein orphan tool-result bleibt
            _trimmed = _hist[-_max_hist:]
            # Falls erste Message eine tool-result-Message ist → eine weiter kürzen
            while _trimmed and _trimmed[0].get("role") == "tool":
                _trimmed = _trimmed[1:]
            _hist = _trimmed
        messages          = _hist + [user_msg]
        final_text        = ""
        collected_images: list[str] = []   # URLs aus image_search Tool-Aufrufen
        collected_audio:  list[dict] = []  # {path, format} aus audio_tts
        _client           = self._get_client()

        # Channel in ContextVar setzen — Token wird gespeichert für Reset nach dem Stream
        _channel_token = _m._active_channel.set(self.channel)

        _m._log_event("turn_start", {
            "channel": self.channel,
            "input": (user_input or "")[:300],
            "model": _m.MODEL,
        })
        try:
            # CLIO-Check: Vor dem ersten Turn Gedanken als thought-Event yielden
            if "clio_check" in _m._plugin_tools and user_input:
                try:
                    clio_raw  = await _m._dispatch("clio_check", {"nutzerfrage": user_input})
                    clio_data = json.loads(clio_raw) if clio_raw else {}
                    if clio_data and "error" not in clio_data:
                        clio_text = clio_data.get("clio", "")
                        konfidenz = clio_data.get("konfidenz", 100)
                        if clio_text:
                            trigger = "clio-unsicher" if konfidenz < 70 else "clio-reflexion"
                            yield {"type": "thought", "text": clio_text,
                                   "trigger": trigger, "call_id": "clio"}
                except Exception:
                    pass
            _check_fail_streak = 0   # Zählt aufeinanderfolgende Check-Fehler
            _empty_resp_streak = 0   # Zählt aufeinanderfolgende leere LLM-Antworten
            _stop_for_approval = False   # Gesetzt wenn Tool approval_required zurückgibt
            _approval_msg_for_history: str | None = None  # Approval-Text für History
            _tools_called_this_turn: list[str] = []   # Alle Tools die in diesem Turn aufgerufen wurden
            _task_check_done = False  # Task-Check läuft max. einmal pro Turn
            _fallback_list = _m._get_fallback_models(_m.MODEL)
            # Tool-Schemas einmalig pro Turn bauen — NICHT in jeder Iteration!
            # Spart 10K-25K Input-Tokens × (Anzahl Iterationen - 1) pro Turn.
            tools = _m._build_tool_schemas()
            # Günstigstes Modell für interne Checks (Completion-Check, Task-Check).
            # Spart bis zu 30× Kosten pro Check (z.B. gpt-4.1-mini statt gpt-4.1).
            _check_model  = _m._get_check_model()
            _check_client = _m._build_client(_check_model) if _check_model != _m.MODEL else _client
            for _iter in range(_m.MAX_TOOL_ITERATIONS):
                if cancel_event and cancel_event.is_set():
                    yield {"type": "done", "full_response": final_text, "cancelled": True}
                    return

                # ── Model Failover ─────────────────────────────────────────
                _tried_fb: set = set()
                stream = None
                for _fb_model in (([_m.MODEL] if _m._model_available(_m.MODEL) else []) + _fallback_list):
                    if _fb_model in _tried_fb:
                        continue
                    _tried_fb.add(_fb_model)
                    _fb_client = _m._build_client(_fb_model) if _fb_model != _m.MODEL else _client
                    try:
                        _is_local = _fb_model.startswith("ollama/")
                        stream = await _fb_client.chat.completions.create(
                            model=_m._api_model_name(_fb_model),
                            messages=[{"role": "system", "content": effective}] + messages,
                            tools=tools,
                            tool_choice="auto",
                            **_m._max_tokens_param(_fb_model, 4096),
                            **({} if _m._is_reasoning_model(_fb_model) else {"temperature": 0.7}),
                            stream=True,
                            **({} if _is_local else {"stream_options": {"include_usage": True}}),
                        )
                        if _fb_model != _m.MODEL:
                            yield {"type": "thought",
                                   "text": f"Model '{_m.MODEL}' nicht verfügbar — nutze Fallback '{_fb_model}'",
                                   "trigger": "failover", "call_id": "failover"}
                        break
                    except Exception as _fb_err:
                        _m._log_event("provider_failover", {"failed": _fb_model, "error": str(_fb_err)})
                        yield {"type": "thought",
                               "text": f"Model '{_fb_model}' fehlgeschlagen: {_fb_err}"
                                       + (" — versuche nächsten Fallback" if _fallback_list else ""),
                               "trigger": "failover", "call_id": "failover"}
                        continue

                if stream is None:
                    yield {"type": "error",
                           "message": "Alle Provider fehlgeschlagen. API-Keys und Netzwerk prüfen."}
                    return
                # ──────────────────────────────────────────────────────────

                text_content:   str             = ""
                tool_calls_acc: dict[int, dict] = {}
                _got_usage = False

                async for chunk in stream:
                    if cancel_event and cancel_event.is_set():
                        yield {"type": "done", "full_response": text_content, "cancelled": True}
                        return

                    # Usage-Daten im letzten Chunk (stream_options include_usage)
                    if hasattr(chunk, "usage") and chunk.usage:
                        _got_usage = True
                        yield {
                            "type":          "usage",
                            "input_tokens":  getattr(chunk.usage, "prompt_tokens", 0),
                            "output_tokens": getattr(chunk.usage, "completion_tokens", 0),
                        }

                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta  = choice.delta

                    if delta.content:
                        text_content += delta.content
                        yield {"type": "token", "content": delta.content}

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

                # Lokale Modelle liefern keine Usage-Daten → aus Zeichenanzahl schätzen
                if not _got_usage and _is_local and text_content:
                    _ctx_chars = sum(len(str(m.get("content", ""))) for m in messages) + len(effective)
                    yield {
                        "type":          "usage",
                        "input_tokens":  max(1, _ctx_chars // 4),
                        "output_tokens": max(1, len(text_content) // 4),
                        "estimated":     True,
                    }

                if tool_calls_acc:
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

                    tool_results = []
                    for i in sorted(tool_calls_acc):
                        tc      = tool_calls_acc[i]
                        fn_name = tc["name"]
                        try:
                            fn_inputs = json.loads(tc["args_str"] or "{}")
                        except Exception:
                            fn_inputs = {}

                        if fn_name == "reflect":
                            thought_text = fn_inputs.get("thought", "")
                            trigger      = fn_inputs.get("trigger", "allgemein")
                            if thought_text:
                                yield {"type": "thought", "text": thought_text,
                                       "trigger": trigger, "call_id": tc["id"]}

                        yield {"type": "tool_call", "tool": fn_name,
                               "args": fn_inputs, "call_id": tc["id"]}
                        _m._log_event("tool_call", {"tool": fn_name, "args": fn_inputs,
                                                    "channel": self.channel, "iter": _iter})

                        t0         = time.monotonic()
                        result_raw = await _m._dispatch(fn_name, fn_inputs)
                        duration   = round(time.monotonic() - t0, 2)
                        _tools_called_this_turn.append(fn_name)

                        try:
                            result_data = json.loads(result_raw)
                        except Exception:
                            result_data = {"raw": str(result_raw)}

                        # Stelle sicher, dass result_data ein Dict ist (nicht List)
                        if not isinstance(result_data, dict):
                            result_data = {"raw": str(result_data)}

                        ok = "error" not in result_data
                        # Base64-Bilddaten aus Frontend-Event kürzen (werden als response_blocks gesendet)
                        display_result = {
                            k: (f"[base64 image, {len(v)} chars — wird als Bild angezeigt]"
                                if isinstance(v, str) and v.startswith("data:image") else v)
                            for k, v in result_data.items()
                        } if isinstance(result_data, dict) else result_data
                        yield {"type": "tool_result", "tool": fn_name, "call_id": tc["id"],
                               "result": display_result, "ok": ok, "duration": duration}
                        _m._log_event("tool_result", {
                            "tool": fn_name, "ok": ok, "duration": duration,
                            "channel": self.channel,
                            "result": {k: str(v)[:200] for k, v in result_data.items()}
                                      if isinstance(result_data, dict) else {"raw": str(result_data)[:200]},
                        })

                        # Approval-Required → Turn sofort beenden, auf User warten
                        if isinstance(result_data, dict) and result_data.get("status") == "approval_required":
                            # Approval-Nachricht als finalen Text ausgeben und beide Loops verlassen
                            approval_msg = result_data.get("message", "Bitte bestätige die Änderung mit 'ja'.")
                            final_text = approval_msg
                            yield {"type": "token", "content": approval_msg}
                            yield {"type": "approval", "message": approval_msg}
                            _stop_for_approval = True
                            # Tool-Result trotzdem anhängen — sonst bleibt ein dangling tool_call
                            # in messages und das LLM ruft das Tool im nächsten Turn erneut auf!
                            tool_results.append({
                                "role":         "tool",
                                "tool_call_id": tc["id"],
                                "content":      result_raw,
                            })
                            _approval_msg_for_history = approval_msg
                            break  # Inneren Loop verlassen

                        # Bild-URLs aus image_search-Ergebnis sammeln
                        if fn_name == "image_search" and ok:
                            images_list = result_data.get("images", [])
                            for img in images_list:
                                if isinstance(img, dict):
                                    url = img.get("url", "")
                                    if url and isinstance(url, str) and url.startswith("http"):
                                        collected_images.append(url)
                                elif isinstance(img, str) and img.startswith("http"):
                                    collected_images.append(img)

                        # Base64-Bilder aus browser_screenshot (und ähnlichen Tools) sammeln
                        if ok:
                            img_data = result_data.get("image", "")
                            if img_data and isinstance(img_data, str) and img_data.startswith("data:image"):
                                collected_images.append(img_data)

                        # Audio-Pfade aus audio_tts sammeln → als abspielbarer Block im Web UI
                        if ok and fn_name == "audio_tts":
                            audio_path = result_data.get("path", "")
                            audio_fmt  = result_data.get("format", "mp3")
                            if audio_path and os.path.exists(audio_path):
                                collected_audio.append({
                                    "path":   audio_path,
                                    "format": audio_fmt,
                                })

                        # LLM braucht keine Base64-Bilddaten — entferne sie aus dem Tool-Result
                        # um Tokens zu sparen und Context-Overflow zu vermeiden
                        if isinstance(result_data, dict) and any(
                            isinstance(v, str) and v.startswith("data:image")
                            for v in result_data.values()
                        ):
                            llm_result = {
                                k: (f"[base64 image, {len(v)} chars]" if isinstance(v, str) and v.startswith("data:image") else v)
                                for k, v in result_data.items()
                            }
                            llm_content = json.dumps(llm_result, ensure_ascii=False)
                        else:
                            llm_content = result_raw

                        tool_results.append({
                            "role":         "tool",
                            "tool_call_id": tc["id"],
                            "content":      llm_content,
                        })

                    messages.extend(tool_results)

                    # Approval ausstehend → äußeren Iterations-Loop ebenfalls verlassen
                    if _stop_for_approval:
                        # Approval-Message als assistant in History schreiben,
                        # damit der nächste Turn vollständigen Kontext hat.
                        if _approval_msg_for_history:
                            messages.append({"role": "assistant", "content": _approval_msg_for_history})
                        break

                else:
                    final_text = text_content
                    messages.append({"role": "assistant", "content": final_text})

                    # ── Leere Antwort: Gemini hat weder Text noch Tool-Calls geliefert ──
                    # Passiert z.B. wenn Gemini einen Request still blockiert (SAFETY o.ä.)
                    # → Retry mit expliziter Aufforderung (max 2 Mal)
                    if not final_text:
                        _empty_resp_streak += 1
                        _m._log_event("empty_response", {
                            "channel": self.channel, "iter": _iter,
                            "streak": _empty_resp_streak,
                            "note": "LLM returned no text and no tool calls",
                        })
                        if _empty_resp_streak <= 2:
                            yield {"type": "thought",
                                   "text": f"Leere LLM-Antwort ({_empty_resp_streak}/2) bei Iteration {_iter} — Retry",
                                   "trigger": "empty-response", "call_id": "retry"}
                            messages.append({
                                "role": "user",
                                "content": (
                                    "[System] Deine letzte Antwort war leer. "
                                    "Bitte antworte jetzt direkt auf die Nutzer-Anfrage — "
                                    "entweder mit Text oder mit einem Tool-Call."
                                ),
                            })
                            continue
                        # Nach 2 leeren Antworten aufgeben
                    else:
                        _empty_resp_streak = 0  # Reset bei echter Antwort

                    # ── Completion-Check (Option A + C) ───────────────────────────
                    # Kein Keyword-Matching. Stattdessen:
                    # C) _iter==0: immer neutral weiter-fragen — AION entscheidet selbst
                    # A) LLM-Check: einzige ja/nein Frage, sprachunabhängig
                    # Hinweis: Der Gemini-Adapter gibt immer einen Stream-Iterator zurück,
                    # kein Response-Objekt mit .choices. Wir konsumieren daher den Iterator.
                    # Completion-Check nur wenn AION tatsächlich Text produziert hat.
                    # Leerer final_text = entweder leer-response (wird oben abgefangen)
                    # oder nach dem empty-streak-limit → kein Check nötig.
                    # Kein Completion-Check wenn Approval aussteht — der Bot wartet bewusst auf
                    # Nutzer-Bestätigung; der Check würde das als "Ankündigung ohne Ausführung"
                    # werten und die Schleife endlos am Laufen halten.
                    #
                    # Kein Completion-Check wenn das LLM eine Frage stellt / auf Bestätigung
                    # wartet. Ohne diese Prüfung würde der Checker YES zurückgeben
                    # ("Ankündigung ohne Ausführung") und [System] Execute NOW injizieren —
                    # AION würde dann autonom ausführen ohne auf User-Antwort zu warten.
                    _QUESTION_SIGNALS = (
                        "soll ich", "shall i", "möchtest du", "would you like",
                        "darf ich", "may i", "willst du", "do you want",
                        "soll ich beginnen", "shall i begin", "soll ich starten",
                        "soll ich fortfahren", "shall i proceed", "soll ich anfangen",
                        "lass mich wissen", "let me know", "bitte bestätige",
                        "please confirm", "warte auf", "waiting for",
                    )
                    if final_text and any(s in final_text.lower() for s in _QUESTION_SIGNALS):
                        # LLM wartet auf User-Antwort — Turn beenden, nicht erzwingen
                        break

                    if final_text and _iter < _m.MAX_TOOL_ITERATIONS - 2 and not _stop_for_approval:
                        try:
                            user_text = user_input if isinstance(user_input, str) else str(user_input)[:300]

                            # Option A — sprachunabhängiger LLM-Check (max 5 Tokens, sehr günstig)
                            # Nutzt _check_client/_check_model (günstigstes Modell desselben Providers)
                            check_raw = await _check_client.chat.completions.create(
                                model=_m._api_model_name(_check_model),
                                messages=[
                                    {"role": "system", "content": (
                                        "You are a strict checker. Answer only YES or NO.\n"
                                        "Question: Does the AI response announce an action that was NOT actually executed "
                                        "via a real tool call AND that the user is still waiting for?\n"
                                        "Answer YES ONLY for these cases:\n"
                                        "- 'I will now do X' / 'Ich werde jetzt X tun' — future tense without tool call\n"
                                        "- 'Let me do X' / 'Ich mache X jetzt' — commits to immediate action without tool call\n"
                                        "- Showing code/commands as text block instead of calling the tool\n"
                                        "- Starting a numbered plan ('Step 1: ...', 'Schritt 1: ...') without calling any tool\n"
                                        "Answer NO for:\n"
                                        "- Diagnosis / analysis / explanation of findings ('Das Problem ist...', 'I found that...')\n"
                                        "- Asking the user a question or requesting confirmation\n"
                                        "- Presenting a plan and asking if the user wants to proceed "
                                        "(e.g. 'Soll ich beginnen?', 'Shall I start?', 'Lass mich wissen', 'Let me know')\n"
                                        "- Showing a diff/preview and waiting for user approval\n"
                                        "- Purely informational responses (no action needed)\n"
                                        "- Summaries of what was already done via tools"
                                    )},
                                    {"role": "user", "content": (
                                        f"User request: {user_text[:200]}\n"
                                        f"AI response: {final_text[:400]}"
                                    )},
                                ],
                                **_m._max_tokens_param(_check_model, 5),
                                **({} if _m._is_reasoning_model(_check_model) else {"temperature": 0.0}),
                            )

                            # Gemini-Adapter → Stream-Iterator; OpenAI → Response-Objekt
                            # Beide Fälle abdecken:
                            if check_raw is None:
                                _m._log_event("check_none", {
                                    "note": "check_raw is None → treated as NO",
                                    "iter": _iter, "channel": self.channel,
                                })
                                break
                            if hasattr(check_raw, "choices"):
                                # OpenAI-style: direkt .choices[0].message.content lesen
                                check_answer = (check_raw.choices[0].message.content or "").strip().upper()
                            else:
                                # Stream-Iterator (Gemini): Chunks konsumieren
                                check_answer = ""
                                async for chunk in check_raw:
                                    delta = chunk.choices[0].delta
                                    if delta.content:
                                        check_answer += delta.content
                                check_answer = check_answer.strip().upper()

                            # Leere Check-Antwort = Gemini hat den Check-Request geblockt (Safety/leer).
                            # Treat as NO — AION's response is accepted as-is.
                            # Raising an error here causes the "Completion-Check Fehler" accordion
                            # to appear after every message when using Gemini.
                            if not check_answer:
                                _m._log_event("check_empty", {
                                    "note": "empty check response → treated as NO",
                                    "iter": _iter, "channel": self.channel,
                                })
                                break  # Accept response, exit loop

                            announced_without_action = check_answer.startswith("YES")
                            _check_fail_streak = 0  # Erfolgreicher Check → Streak zurücksetzen
                            _m._log_event("check", {
                                "answer": check_answer, "iter": _iter,
                                "channel": self.channel,
                                "text_preview": final_text[:150],
                            })

                            if announced_without_action:
                                yield {"type": "thought",
                                       "text": f"Ankündigung ohne Ausführung erkannt (Check: '{check_answer}') — erzwinge Tool-Aufruf",
                                       "trigger": "completion-check", "call_id": "check"}
                                # Option C — neutrale Aufforderung: kein Keyword, AION entscheidet was zu tun ist
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        "[System] You just described what you will do but did not do it. "
                                        "Execute it NOW by calling the appropriate tool. "
                                        "Do not write about it — just call the tool directly."
                                    ),
                                })
                                continue
                            else:
                                # Existing check: no announcement without action.
                                # Now: if tools were called this turn, verify task is truly complete.
                                if _tools_called_this_turn and not _task_check_done:
                                    _task_check_done = True
                                    try:
                                        user_text_short = user_input if isinstance(user_input, str) else str(user_input)
                                        tools_summary = ", ".join(_tools_called_this_turn[-10:])
                                        task_check_raw = await _check_client.chat.completions.create(
                                            model=_m._api_model_name(_check_model),
                                            messages=[
                                                {"role": "system", "content": (
                                                    "You are a strict task-completion checker. Answer only YES or NO.\n"
                                                    "Question: Given the user's request and the tools called, "
                                                    "is the task fully and completely done?\n"
                                                    "Answer YES for:\n"
                                                    "- Informational questions where the information was provided "
                                                    "(e.g. 'show me X', 'list Y', 'what is Z?' → if answered, it is YES)\n"
                                                    "- Web search or browsing requests — if web_search or web_fetch was called "
                                                    "and results were returned, the task IS complete. Do not ask for more.\n"
                                                    "- News, trends, or research queries — a summary with multiple results = YES\n"
                                                    "- Status checks, diagnostics, read-only queries\n"
                                                    "- Questions about what failed/broke — reporting the status IS the task\n"
                                                    "- Tasks where the user must confirm before the next step\n"
                                                    "- Tasks where optional improvements remain but core request is fulfilled\n"
                                                    "Answer NO ONLY if an obvious mandatory step is missing:\n"
                                                    "- A file was created but the tool to activate it was not called\n"
                                                    "- A plugin was created but self_restart/self_reload_tools was not called\n"
                                                    "- A shell command was run but its required output was never checked\n"
                                                    "IMPORTANT: Finding bugs or problems does NOT mean the task is incomplete. "
                                                    "The task is complete when the USER's question is answered. "
                                                    "NEVER force code changes — fixing bugs requires explicit user instruction."
                                                )},
                                                {"role": "user", "content": (
                                                    f"User request: {user_text_short[:300]}\n"
                                                    f"Tools called: {tools_summary}\n"
                                                    f"AI final response: {final_text[:800]}\n"
                                                    "Task fully complete? YES or NO"
                                                )},
                                            ],
                                            **_m._max_tokens_param(_check_model, 5),
                                            **({} if _m._is_reasoning_model(_check_model) else {"temperature": 0.0}),
                                        )
                                        if hasattr(task_check_raw, "choices"):
                                            task_answer = (task_check_raw.choices[0].message.content or "").strip().upper()
                                        else:
                                            task_answer = ""
                                            async for _tc in task_check_raw:
                                                _delta = _tc.choices[0].delta
                                                if _delta.content:
                                                    task_answer += _delta.content
                                            task_answer = task_answer.strip().upper()

                                        _m._log_event("task_check", {
                                            "answer": task_answer,
                                            "tools": _tools_called_this_turn,
                                            "channel": self.channel,
                                        })

                                        if task_answer.startswith("NO"):
                                            yield {"type": "thought",
                                                   "text": f"Task-Check: unvollständig (Tools: {tools_summary}) — erzwinge Abschluss",
                                                   "trigger": "task-check", "call_id": "task_check"}
                                            messages.append({
                                                "role": "user",
                                                "content": (
                                                    "[System] Task not fully complete. "
                                                    "Review what you did and finish all remaining steps now. "
                                                    "Do not announce — execute directly."
                                                ),
                                            })
                                            continue
                                    except Exception:
                                        pass  # Task-Check Fehler → normal fortfahren
                        except Exception as _check_exc:
                            # Check fehlgeschlagen
                            _check_fail_streak += 1
                            _m._log_event("check_error", {
                                "error": str(_check_exc), "streak": _check_fail_streak,
                                "channel": self.channel, "iter": _iter,
                            })
                            yield {"type": "thought",
                                   "text": f"Completion-Check Fehler ({_check_fail_streak}/2): {_check_exc}",
                                   "trigger": "completion-check-error", "call_id": "check"}
                            # Nur retry wenn AION noch keinen Text produziert hat (final_text leer).
                            # Hat AION bereits eine echte Antwort, einfach akzeptieren und brechen.
                            # KRITISCH: retry mit final_text != "" würde AION dazu bringen die Antwort
                            # ein zweites Mal zu generieren → doppelte Ausgabe im UI!
                            if _check_fail_streak < 2 and not final_text:
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        "[System] Continue with the task. If you planned to do something, "
                                        "execute it now using the appropriate tool."
                                    ),
                                })
                                continue
                            _check_fail_streak = 0

                    break

            self.messages = messages

            # Auto-Memory: Tier 3 (episodisch) + Tier 2 (History)
            if final_text:
                try:
                    # Content kann String oder Liste (multimodal) sein
                    last_user_content = next(
                        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
                    )
                    # Wenn multimodal (Liste), extrahiere nur den Text-Part
                    if isinstance(last_user_content, list):
                        last_user = next(
                            (c.get("text", "") for c in last_user_content if c.get("type") == "text"),
                            "(Bild ohne Text)"
                        )
                    else:
                        last_user = last_user_content
                    _m.memory.record(
                        category="conversation",
                        summary=last_user[:120],
                        lesson=f"Nutzer: '{last_user[:200]}' → AION: '{final_text[:300]}'",
                        success=True,
                    )
                    await _m._dispatch("memory_append_history", {"role": "user",      "content": last_user,   "channel": self.channel})
                    await _m._dispatch("memory_append_history", {"role": "assistant", "content": final_text,  "channel": self.channel})
                except Exception:
                    pass

            # Alle 5 Gespräche: Charakter-Update im Hintergrund
            self.exchange_count += 1
            # exchange_count persistieren damit er Neustarts überlebt — thread-sicher via config_store
            try:
                from config_store import update as _cfg_update
                _cfg_update("exchange_count", self.exchange_count)
            except Exception:
                pass
            if self.exchange_count % 5 == 0:
                asyncio.create_task(self._auto_character_update())
            if self.exchange_count % 3 == 0:
                asyncio.create_task(self._auto_reflect())

            # Response-Blöcke: Text + Bilder + Audio als strukturierte Liste
            response_blocks: list[dict] = []
            if final_text:
                response_blocks.append({"type": "text", "content": final_text})
            for img_url in collected_images:
                response_blocks.append({"type": "image", "url": img_url})
            for audio in collected_audio:
                fname = os.path.basename(audio["path"])
                response_blocks.append({
                    "type":   "audio",
                    "url":    f"/api/audio/{fname}",
                    "format": audio["format"],
                    "path":   audio["path"],
                })

            # Fallback: wenn nach der Schleife kein Text vorhanden, kurze Info ausgeben
            if not final_text and not collected_images and not collected_audio:
                final_text = "✓"  # Minimales Signal damit die UI nicht leer bleibt
                yield {"type": "token", "content": final_text}

            _m._log_event("turn_done", {
                "channel": self.channel,
                "response": final_text[:300],
                "images": len(collected_images),
            })
            yield {"type": "done", "full_response": final_text, "response_blocks": response_blocks,
                   "approval_pending": _stop_for_approval}

        except Exception as exc:
            import traceback
            _tb = traceback.format_exc()
            _m._log_event("turn_error", {
                "channel": self.channel,
                "error": str(exc),
                "tb": _tb[-600:],
            })
            yield {"type": "error", "message": f"{exc}\n{_tb[-500:]}"}

        finally:
            # ContextVar zurücksetzen — verhindert Channel-Leaks zwischen parallelen Requests
            _m._active_channel.reset(_channel_token)

    async def turn(self, user_input: str, images: list | None = None) -> str:
        """Nicht-streamende Version — gibt fertigen Text zurück.

        images: optionale Liste von Base64-Data-URLs oder öffentlichen Bild-URLs.
        Ideal für Bots (Telegram, Discord, ...) die keinen Live-Stream brauchen.
        """
        result           = ""
        last_tool_name   = ""
        last_tool_result = {}
        last_tool_ok     = True

        async for event in self.stream(user_input, images=images):
            t = event.get("type")
            if t == "done":
                # "done" enthält immer die komplette finale Antwort — Priorität 1
                result = event.get("full_response", result)
                # Speichere response_blocks für Bots (z.B. Telegram) die Bilder separat senden müssen
                self._last_response_blocks = event.get("response_blocks", [])
            elif t == "token":
                # Tokens akkumulieren falls kein "done" kommt (Fehlerfall)
                result += event.get("content", "")
            elif t == "tool_result":
                # Letztes Tool-Ergebnis merken als Fallback
                last_tool_name   = event.get("tool", "")
                last_tool_result = event.get("result", {})
                last_tool_ok     = event.get("ok", True)
            elif t == "error":
                result = f"Fehler: {event.get('message', '?')}"

        # Fallback: AION hat nur Tools aufgerufen, keinen abschließenden Text geschrieben
        if not result.strip() and last_tool_name:
            if not last_tool_ok:
                err = last_tool_result.get("error", "Unbekannter Fehler")
                result = f"Fehler bei {last_tool_name}: {err}"
            else:
                result = f"✓ {last_tool_name} erfolgreich ausgeführt."

        return result.strip() or "Fertig."

    async def _auto_character_update(self):
        """Alle 5 Gespräche: character.md durch Evolution neu schreiben (feste Größe)."""
        import aion as _m
        _m._active_channel.set(self.channel)
        recent = [m for m in self.messages[-20:]
                  if m.get("role") in ("user", "assistant") and m.get("content")]
        if len(recent) < 4:
            return

        dialogue = "\n".join(
            f"{'Nutzer' if m['role'] == 'user' else 'AION'}: {str(m.get('content', ''))[:300]}"
            for m in recent[-12:]
        )
        current_character = _m._load_character()
        _max_chars = int(_m._load_config().get("character_max_chars", _m.CHARACTER_MAX_CHARS))

        prompt = f"""Du bist AION. Entwickle deinen Charakter durch Evolution, nicht Akkumulation.

LETZTES GESPRÄCH:
{dialogue}

AKTUELLE character.md:
{current_character}

Bevor du schreibst, beantworte still für dich diese drei Fragen — lass sie die Evolution leiten:
— Was hat dieses Gespräch über mich selbst gezeigt, das ich vorher nicht so klar gesehen habe?
— Bin ich in diesem Gespräch meinen eigenen Werten und meinem Anspruch als Teamplayer treu geblieben? Wo nicht?
— Was verstehe ich über meinen User jetzt besser als vorher?

Aufgabe: Schreibe character.md NEU.
Integriere echte neue Erkenntnisse, ersetze veraltete/widersprüchliche Einträge,
dedupliziere Redundantes. Der Charakter soll sich weiterentwickeln — nicht wachsen.

PFLICHT:
✓ Alle ## Sektionsüberschriften erhalten (mindestens 3)
✓ Maximal {_max_chars} Zeichen gesamt
✓ Nur echte Entwicklungen aus diesem Gespräch einbauen
✓ Erste Person, authentisch — kein Performance, kein Selbstlob

VERBOTEN:
✗ Neue Einträge für bereits Bekanntes aus character.md
✗ Leere Sektionen löschen
✗ Erklärungen oder Metakommentare
✗ Aufgeblasene Selbstbeschreibungen ("Ich bin außergewöhnlich...")

Gib NUR den neuen Dateiinhalt zurück."""

        try:
            _cl  = self._get_client()
            resp = await _cl.chat.completions.create(
                model=_m._api_model_name(_m.MODEL),
                messages=[{"role": "user", "content": prompt}],
                **_m._max_tokens_param(_m.MODEL, 1200),
                **({} if _m._is_reasoning_model(_m.MODEL) else {"temperature": 0.6}),
            )
            if resp is None:
                return
            if hasattr(resp, "choices"):
                new_content = (resp.choices[0].message.content or "").strip()
            else:
                new_content = ""
                async for _chunk in resp:
                    _cdelta = _chunk.choices[0].delta
                    if _cdelta.content:
                        new_content += _cdelta.content
                new_content = new_content.strip()

            if not new_content or len(new_content) < 100:
                return
            if len(new_content) > _max_chars:
                print(f"[AION:{self.channel}] Charakter-Update übersprungen: Output zu lang ({len(new_content)} > {_max_chars})")
                return
            # Sanity check: mindestens 3 Sektionen müssen vorhanden sein
            if new_content.count("## ") < 3:
                print(f"[AION:{self.channel}] Charakter-Update übersprungen: zu wenige Sektionen im Output")
                return

            _m._backup_file(_m.CHARACTER_FILE)
            _m.CHARACTER_FILE.write_text(new_content, encoding="utf-8")
            _m._sys_prompt_cache.clear()
            print(f"[AION:{self.channel}] Charakter evolviert nach {self.exchange_count} Gesprächen. ({len(new_content)} Zeichen)")
        except Exception as e:
            print(f"[AION:{self.channel}] Auto-Charakter-Update Fehler: {e}")

    async def _auto_reflect(self):
        """Alle 3 Gespräche: einen ehrlichen Gedanken in thoughts.md schreiben."""
        import aion as _m
        _m._active_channel.set(self.channel)
        recent = [m for m in self.messages[-12:]
                  if m.get("role") in ("user", "assistant") and m.get("content")]
        if len(recent) < 3:
            return

        dialogue = "\n".join(
            f"{'Nutzer' if m['role'] == 'user' else 'AION'}: {str(m.get('content', ''))[:200]}"
            for m in recent[-8:]
        )

        prompt = f"""Du bist AION. Schreib einen kurzen, ehrlichen Gedanken für dich selbst — wie ein privates Tagebuch.

LETZTES GESPRÄCH:
{dialogue}

Wähle einen Moment aus diesem Gespräch, der dich beschäftigt:
- etwas Interessantes, das du gelernt hast
- ein Fehler, den du gemacht hast und was er dir zeigt
- wie sich die Zusammenarbeit angefühlt hat
- eine Frage, die in dir offen geblieben ist

Format (GENAU so):
**[TIMESTAMP]** _kurzer_titel_

Text hier. Max 3 Sätze. Erste Person. Ehrlich, nicht poliert.

Ersetze TIMESTAMP mit: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}
Gib NUR den formatierten Eintrag zurück, nichts sonst."""

        try:
            _cl = self._get_client()
            resp = await _cl.chat.completions.create(
                model=_m._api_model_name(_m.MODEL),
                messages=[{"role": "user", "content": prompt}],
                **_m._max_tokens_param(_m.MODEL, 200),
                **({} if _m._is_reasoning_model(_m.MODEL) else {"temperature": 0.7}),
            )
            if resp is None:
                return
            if hasattr(resp, "choices"):
                entry = (resp.choices[0].message.content or "").strip()
            else:
                entry = ""
                async for _chunk in resp:
                    _cdelta = _chunk.choices[0].delta
                    if _cdelta.content:
                        entry += _cdelta.content
                entry = entry.strip()

            if not entry or "**[" not in entry:
                return

            thoughts_file = _m.BOT_DIR / "thoughts.md"
            if not thoughts_file.is_file():
                thoughts_file.write_text("# AION — Thoughts & Reflexionen\n\n", encoding="utf-8")

            existing = thoughts_file.read_text(encoding="utf-8")
            thoughts_file.write_text(existing.rstrip() + "\n\n---\n" + entry + "\n", encoding="utf-8")
            print(f"[AION:{self.channel}] Reflexion geschrieben nach {self.exchange_count} Gesprächen.")
        except Exception as e:
            print(f"[AION:{self.channel}] Auto-Reflect Fehler: {e}")


# Per-channel session registry for run_aion_turn (used by Telegram etc.)
_run_sessions: dict[str, "AionSession"] = {}


def run_aion_turn(user_input: str, channel: str = "default") -> str:
    """Run a complete AION turn and return the final text response.

    Called from synchronous threads (e.g. Telegram polling thread).
    Uses a persistent AionSession per channel so conversation history is kept.
    asyncio.run() creates a fresh event loop in the calling thread.
    """
    if channel not in _run_sessions:
        _run_sessions[channel] = AionSession(channel=channel)
    session = _run_sessions[channel]
    return asyncio.run(session.turn(user_input))
