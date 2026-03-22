"""
AION Plugin: Telegram Bot (bidirektional)
=========================================
Nutzt AionSession — vollständige Feature-Parität mit dem Web UI:
  - Eigene Konversations-History pro Telegram-User
  - Memory-Injection, Thoughts-Injection
  - Automatischer Charakter-Update alle 5 Gespräche
  - Lange Antworten werden automatisch aufgeteilt
  - Interaktive Bestätigungen via Inline-Buttons (approval_ja / approval_nein)
  - Fotos empfangen und senden (inkl. base64 Screenshots)
  - Sprachnachrichten empfangen (Transkription) und senden (TTS)

Konfiguration (.env):
  TELEGRAM_BOT_TOKEN=1234567890:AAEXAMPLE...
  TELEGRAM_CHAT_ID=123456789   (optional, wird beim ersten /start gespeichert)

Abhängigkeit:
  pip install httpx
"""

import asyncio
import importlib.util
import os
import subprocess
import tempfile
import threading
from pathlib import Path

_TOKEN_FILE  = Path.home() / ".aion_telegram_token"
_CHATID_FILE = Path.home() / ".aion_telegram_chatid"
_polling_lock = threading.Lock()

# ── audio_pipeline Lazy-Import ────────────────────────────────────────────────

_audio_pipeline_mod = None

def _get_audio_pipeline():
    """Lädt das audio_pipeline-Plugin (einmalig, lazy). Gibt Modul oder None zurück."""
    global _audio_pipeline_mod
    if _audio_pipeline_mod is not None:
        return _audio_pipeline_mod
    try:
        _ap_path = Path(__file__).parent.parent / "audio_pipeline" / "audio_pipeline.py"
        if not _ap_path.exists():
            return None
        spec = importlib.util.spec_from_file_location("audio_pipeline", _ap_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _audio_pipeline_mod = mod
        return mod
    except Exception as e:
        print(f"[Telegram] audio_pipeline nicht ladbar: {e}")
        return None


def _get_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token and _TOKEN_FILE.is_file():
        token = _TOKEN_FILE.read_text().strip()
    return token


def _get_chat_id() -> str:
    cid = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not cid and _CHATID_FILE.is_file():
        cid = _CHATID_FILE.read_text().strip()
    return cid


def _save_chat_id(cid: str):
    try:
        _CHATID_FILE.write_text(str(cid))
    except Exception:
        pass


def _api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _md_to_html(text: str) -> str:
    """Konvertiert AION-Markdown in Telegram-kompatibles HTML."""
    import re

    code_blocks: list[str] = []

    def _save_block(m: re.Match) -> str:
        lang    = (m.group(1) or "").strip()
        content = m.group(2)
        content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if lang:
            html = f'<pre><code class="language-{lang}">{content}</code></pre>'
        else:
            html = f"<pre><code>{content}</code></pre>"
        code_blocks.append(html)
        return f"\x00CODE{len(code_blocks) - 1}\x00"

    def _save_inline(m: re.Match) -> str:
        content = m.group(1).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        code_blocks.append(f"<code>{content}</code>")
        return f"\x00CODE{len(code_blocks) - 1}\x00"

    text = re.sub(r"```([^\n`]*)\n(.*?)```", _save_block, text, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+)`", _save_inline, text)

    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__",     r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text, flags=re.DOTALL)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2">\1</a>', text)

    def _blockquote(m: re.Match) -> str:
        inner = re.sub(r"^&gt;\s?", "", m.group(0), flags=re.MULTILINE).strip()
        return f"<blockquote>{inner}</blockquote>"
    text = re.sub(r"(?:^&gt;[^\n]*\n?)+", _blockquote, text, flags=re.MULTILINE)

    text = re.sub(r"^[ \t]*[-*]\s+", "• ", text, flags=re.MULTILINE)

    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODE{i}\x00", block)

    return text.strip()


def _split_message(text: str, max_len: int = 4000) -> list:
    """Splittet Text in Chunks <= max_len Zeichen (an Absätzen wenn möglich)."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip("\n")
    return chunks


# ── Tool: Nachricht senden ────────────────────────────────────────────────────

def send_telegram_message(message: str = "", **_) -> dict:
    """Sendet eine Nachricht an die konfigurierte Telegram-Chat-ID."""
    token = _get_token()
    cid   = _get_chat_id()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN nicht gesetzt."}
    if not cid:
        return {"ok": False, "error": "Keine Chat-ID bekannt. Sende /start an den Bot."}
    try:
        import httpx
        with httpx.Client(timeout=10) as http:
            for chunk in _split_message(message, 4000):
                try:
                    html = _md_to_html(chunk)
                    r = http.post(_api_url(token, "sendMessage"),
                                  json={"chat_id": cid, "text": html, "parse_mode": "HTML"})
                    if not r.is_success:
                        http.post(_api_url(token, "sendMessage"),
                                  json={"chat_id": cid, "text": chunk})
                except Exception:
                    http.post(_api_url(token, "sendMessage"),
                              json={"chat_id": cid, "text": chunk})
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Async Worker ──────────────────────────────────────────────────────────────

async def _telegram_worker(token: str):
    """Vollständig asynchroner Long-Polling Worker."""
    try:
        import httpx
    except ImportError:
        print("[Telegram] 'httpx' nicht installiert — Polling deaktiviert.")
        print("[Telegram] Installieren mit: pip install httpx")
        return

    try:
        from aion import AionSession
    except ImportError:
        print("[Telegram] AionSession nicht gefunden — aion.py zu alt?")
        return

    sessions: dict = {}
    busy: set = set()
    offset = 0
    print("[Telegram] Async Long-Polling Worker gestartet.")

    async with httpx.AsyncClient(timeout=35.0) as http:

        async def _send(chat_id: str, text: str):
            for chunk in _split_message(text, 4000):
                try:
                    html = _md_to_html(chunk)
                    r = await http.post(
                        _api_url(token, "sendMessage"),
                        json={"chat_id": chat_id, "text": html, "parse_mode": "HTML"},
                    )
                    if not r.is_success:
                        await http.post(
                            _api_url(token, "sendMessage"),
                            json={"chat_id": chat_id, "text": chunk},
                        )
                except Exception:
                    try:
                        await http.post(
                            _api_url(token, "sendMessage"),
                            json={"chat_id": chat_id, "text": chunk},
                        )
                    except Exception:
                        pass

        async def _send_photo(chat_id: str, url: str):
            """Sendet ein Bild: data:-URL als Datei-Upload, HTTP-URL direkt."""
            try:
                if url.startswith("data:"):
                    import base64 as _b64
                    header, b64data = url.split(",", 1)
                    mime = header.split(":")[1].split(";")[0]
                    ext = ".jpg" if "jpeg" in mime else ".png"
                    img_bytes = _b64.b64decode(b64data)
                    await http.post(
                        _api_url(token, "sendPhoto"),
                        data={"chat_id": chat_id},
                        files={"photo": (f"screenshot{ext}", img_bytes, mime)},
                    )
                else:
                    await http.post(
                        _api_url(token, "sendPhoto"),
                        json={"chat_id": chat_id, "photo": url},
                    )
            except Exception as e:
                print(f"[Telegram] sendPhoto Fehler: {e}")

        async def _send_voice_reply(chat_id: str, text_reply: str) -> bool:
            """TTS → OGG OPUS → Telegram sendVoice."""
            ap = _get_audio_pipeline()
            if not ap:
                return False
            wav_tmp = ogg_tmp = None
            try:
                loop = asyncio.get_event_loop()
                tts_res = await loop.run_in_executor(None, ap.audio_tts, text_reply)
                if not tts_res.get("ok"):
                    print(f"[Telegram] TTS Fehler: {tts_res.get('error')}")
                    return False
                wav_tmp = tts_res["path"]

                ogg_tmp = wav_tmp.replace(".wav", "_tg.ogg").replace(".mp3", "_tg.ogg")
                if not ogg_tmp.endswith("_tg.ogg"):
                    ogg_tmp = wav_tmp + "_tg.ogg"
                _ap = _get_audio_pipeline()
                _ffmpeg = (_ap._find_ffmpeg() if _ap and hasattr(_ap, "_find_ffmpeg") else None) or "ffmpeg"
                cmd = [_ffmpeg, "-y", "-i", wav_tmp, "-c:a", "libopus", "-b:a", "64k", ogg_tmp]
                proc = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(cmd, capture_output=True, timeout=30),
                )
                if proc.returncode != 0:
                    print(f"[Telegram] ffmpeg OGG-Konvertierung fehlgeschlagen")
                    return False

                with open(ogg_tmp, "rb") as f:
                    r = await http.post(
                        _api_url(token, "sendVoice"),
                        data={"chat_id": chat_id},
                        files={"voice": ("voice.ogg", f, "audio/ogg")},
                    )
                return r.is_success

            except Exception as e:
                print(f"[Telegram] Voice-Reply Fehler: {e}")
                return False
            finally:
                for p in [wav_tmp, ogg_tmp]:
                    if p and os.path.exists(p):
                        try:
                            os.unlink(p)
                        except Exception:
                            pass

        while True:
            try:
                r = await http.get(
                    _api_url(token, "getUpdates"),
                    params={"offset": offset, "timeout": 8},
                )

                if not r.is_success:
                    if r.status_code == 409:
                        _409_streak = getattr(_telegram_worker, "_409_streak", 0) + 1
                        _telegram_worker._409_streak = _409_streak
                        if _409_streak == 1:
                            print("[Telegram] getUpdates HTTP 409 — anderer Client aktiv, warte...")
                        elif _409_streak % 5 == 0:
                            print(f"[Telegram] 409 hält an ({_409_streak}x)")
                        wait = min(10 + _409_streak * 2, 30)
                        await asyncio.sleep(wait)
                    else:
                        print(f"[Telegram] getUpdates HTTP {r.status_code} — Retry in 5s")
                        await asyncio.sleep(5)
                    continue

                _telegram_worker._409_streak = 0

                data = r.json()
                if not data.get("ok"):
                    print(f"[Telegram] API-Fehler: {data.get('description', data)}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    # ── Callback-Query (Inline-Keyboard-Button) ───────────────
                    cq = update.get("callback_query")
                    if cq:
                        cq_id      = cq.get("id", "")
                        cq_data    = cq.get("data", "")
                        cq_msg     = cq.get("message", {})
                        cq_chat_id = str(cq_msg.get("chat", {}).get("id", ""))
                        cq_msg_id  = cq_msg.get("message_id")
                        try:
                            await http.post(_api_url(token, "answerCallbackQuery"),
                                            json={"callback_query_id": cq_id})
                        except Exception:
                            pass
                        if cq_msg_id:
                            try:
                                await http.post(_api_url(token, "editMessageReplyMarkup"),
                                                json={"chat_id": cq_chat_id, "message_id": cq_msg_id,
                                                      "reply_markup": {"inline_keyboard": []}})
                            except Exception:
                                pass
                        if cq_data in ("approval_ja", "approval_nein") and cq_chat_id:
                            approval_text = "ja" if cq_data == "approval_ja" else "nein"
                            _save_chat_id(cq_chat_id)
                            if cq_chat_id not in sessions:
                                sess = AionSession(channel=f"telegram_{cq_chat_id}")
                                await sess.load_history(num_entries=10, channel_filter=f"telegram_{cq_chat_id}")
                                sessions[cq_chat_id] = sess
                            if cq_chat_id not in busy:
                                busy.add(cq_chat_id)
                                async def _cq_typing():
                                    while True:
                                        try:
                                            await http.post(_api_url(token, "sendChatAction"),
                                                            json={"chat_id": cq_chat_id, "action": "typing"})
                                        except Exception:
                                            pass
                                        await asyncio.sleep(4)
                                cq_typing = asyncio.create_task(_cq_typing())
                                cq_resp = ""
                                cq_blocks = []
                                try:
                                    async for event in sessions[cq_chat_id].stream(approval_text):
                                        t2 = event.get("type")
                                        if t2 == "done":
                                            cq_resp   = event.get("full_response", cq_resp)
                                            cq_blocks = event.get("response_blocks", [])
                                        elif t2 == "token":
                                            cq_resp += event.get("content", "")
                                        elif t2 == "error":
                                            cq_resp = f"Fehler: {event.get('message', '?')}"
                                except Exception as e:
                                    cq_resp = f"Fehler: {e}"
                                finally:
                                    cq_typing.cancel()
                                    busy.discard(cq_chat_id)
                                if cq_blocks:
                                    for block in cq_blocks:
                                        if block.get("type") == "text" and block.get("content", "").strip():
                                            await _send(cq_chat_id, block["content"])
                                        elif block.get("type") == "image" and block.get("url"):
                                            await _send_photo(cq_chat_id, block["url"])
                                else:
                                    await _send(cq_chat_id, cq_resp or "Fertig.")
                        continue

                    msg     = update.get("message", {})
                    text    = (msg.get("text") or msg.get("caption") or "").strip()
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    photos  = msg.get("photo", [])
                    voice   = msg.get("voice") or msg.get("audio")

                    if not chat_id:
                        continue

                    # ── Nicht unterstützte Dateitypen ─────────────────────────
                    _unsupported_label = None
                    _video      = msg.get("video")
                    _document   = msg.get("document")
                    _sticker    = msg.get("sticker")
                    _animation  = msg.get("animation")
                    _video_note = msg.get("video_note")
                    _contact    = msg.get("contact")
                    _location   = msg.get("location")

                    if _video:
                        fname   = _video.get("file_name", "")
                        size_mb = round(_video.get("file_size", 0) / 1_048_576, 1)
                        dur     = _video.get("duration", 0)
                        _unsupported_label = f"Video{' «' + fname + '»' if fname else ''} ({dur}s, {size_mb} MB)"
                    elif _document:
                        fname   = _document.get("file_name", "?")
                        mime    = _document.get("mime_type", "")
                        size_kb = round(_document.get("file_size", 0) / 1024)
                        _unsupported_label = f"Datei «{fname}»{' (' + mime + ')' if mime else ''} ({size_kb} KB)"
                    elif _sticker:
                        emoji = _sticker.get("emoji", "")
                        _unsupported_label = f"Sticker {emoji}".strip()
                    elif _animation:
                        _unsupported_label = "GIF / Animation"
                    elif _video_note:
                        dur = _video_note.get("duration", 0)
                        _unsupported_label = f"Videonachricht ({dur}s)"
                    elif _contact:
                        name = (_contact.get("first_name", "") + " " + _contact.get("last_name", "")).strip()
                        _unsupported_label = f"Kontakt «{name}»"
                    elif _location:
                        lat = _location.get("latitude", "?")
                        lon = _location.get("longitude", "?")
                        _unsupported_label = f"Standort ({lat}, {lon})"

                    if _unsupported_label:
                        import aion as _aion_core
                        msg_text = (
                            _aion_core.unsupported_file_message(_unsupported_label)
                            if hasattr(_aion_core, "unsupported_file_message")
                            else (
                                f"📥 Empfangen: {_unsupported_label}\n\n"
                                "Dieses Format kann ich leider noch nicht verarbeiten. "
                                "Sag mir Bescheid, wenn ich ein Plugin dafür erstellen soll."
                            )
                        )
                        await _send(chat_id, msg_text)
                        continue

                    if not text and not photos and not voice:
                        continue

                    _save_chat_id(chat_id)

                    if text.startswith("/start"):
                        await _send(chat_id,
                            "AION Telegram-Bot aktiviert!\n"
                            f"Chat-ID: {chat_id}\n"
                            "Schreib mir einfach — du kannst auch Bilder und Sprachnachrichten senden!")
                        continue

                    # Session pro User
                    if chat_id not in sessions:
                        sess = AionSession(channel=f"telegram_{chat_id}")
                        await sess.load_history(num_entries=10, channel_filter=f"telegram_{chat_id}")
                        sessions[chat_id] = sess

                    # Foto(s) als Base64 laden
                    images = []
                    if photos:
                        best = max(photos, key=lambda p: p.get("file_size", 0))
                        try:
                            fr = await http.get(_api_url(token, "getFile"),
                                                params={"file_id": best["file_id"]})
                            file_path = fr.json()["result"]["file_path"]
                            img_r = await http.get(
                                f"https://api.telegram.org/file/bot{token}/{file_path}"
                            )
                            import base64
                            mime = "image/jpeg" if file_path.endswith(".jpg") else "image/png"
                            b64  = base64.b64encode(img_r.content).decode()
                            images.append(f"data:{mime};base64,{b64}")
                        except Exception as e:
                            print(f"[Telegram] Bild-Download Fehler: {e}")

                    # Voice/Audio transkribieren
                    is_voice_input = False
                    if voice and not text:
                        tmp_audio_path = None
                        try:
                            fr = await http.get(
                                _api_url(token, "getFile"),
                                params={"file_id": voice["file_id"]},
                            )
                            remote_path = fr.json().get("result", {}).get("file_path", "")
                            audio_bytes = (
                                await http.get(
                                    f"https://api.telegram.org/file/bot{token}/{remote_path}"
                                )
                            ).content
                            mime = voice.get("mime_type", "audio/ogg")
                            ext  = ".mp3" if "mp3" in mime else ".m4a" if "m4a" in mime else ".ogg"
                            tmp  = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                            tmp.write(audio_bytes)
                            tmp.close()
                            tmp_audio_path = tmp.name

                            ap = _get_audio_pipeline()
                            if ap:
                                res = ap.audio_transcribe_any(tmp_audio_path)
                                if res.get("ok") and res.get("text", "").strip():
                                    text = res["text"].strip()
                                    is_voice_input = True
                                    print(f"[Telegram] Sprachnachricht -> '{text[:70]}'")
                                else:
                                    text = f"[Sprachnachricht — Transkription fehlgeschlagen: {res.get('error', '?')}]"
                            else:
                                text = "[audio_pipeline nicht verfügbar]"
                        except Exception as _ve:
                            print(f"[Telegram] Voice-Fehler: {type(_ve).__name__}: {_ve}")
                            text = f"[Fehler bei Sprachnachricht: {type(_ve).__name__}]"
                        finally:
                            if tmp_audio_path and os.path.exists(tmp_audio_path):
                                try:
                                    os.unlink(tmp_audio_path)
                                except Exception:
                                    pass

                    if chat_id in busy:
                        await _send(chat_id, "⏳ Ich bin noch am Antworten — bitte warten...")
                        continue

                    # Typing-Keepalive
                    async def _typing_keepalive():
                        while True:
                            try:
                                await http.post(_api_url(token, "sendChatAction"),
                                                json={"chat_id": chat_id, "action": "typing"})
                            except Exception:
                                pass
                            await asyncio.sleep(4)

                    busy.add(chat_id)
                    typing_task     = asyncio.create_task(_typing_keepalive())
                    response        = ""
                    response_blocks = []
                    needs_approval  = False
                    tg_tool_sent    = False
                    try:
                        async for event in sessions[chat_id].stream(
                            text, images=images or None
                        ):
                            t = event.get("type")
                            if t == "done":
                                response        = event.get("full_response", response)
                                response_blocks = event.get("response_blocks", [])
                            elif t == "token":
                                response += event.get("content", "")
                            elif t == "approval":
                                needs_approval = True
                            elif t == "error":
                                response = f"Fehler: {event.get('message', '?')}"
                            elif t == "tool_result":
                                if event.get("tool") in ("send_telegram_message", "send_telegram_voice"):
                                    tg_tool_sent = True
                    except Exception as e:
                        response = f"Fehler: {e}"
                        print(f"[Telegram] stream() Fehler für {chat_id}: {e}")
                    finally:
                        typing_task.cancel()
                        busy.discard(chat_id)

                    if tg_tool_sent:
                        # AION hat Text schon via Tool gesendet — Bilder trotzdem liefern
                        image_blocks = [b for b in response_blocks if b.get("type") == "image" and b.get("url")]
                        for block in image_blocks:
                            await _send_photo(chat_id, block["url"])
                        # Bei Sprachnachricht-Input: Voice-Antwort trotzdem schicken (response enthält finalen Text)
                        if is_voice_input and response.strip():
                            await _send_voice_reply(chat_id, response)
                        continue
                    if not response.strip() and not response_blocks:
                        response = "Fertig."

                    # Inline-Keyboard für Bestätigungen
                    approval_keyboard = {
                        "inline_keyboard": [[
                            {"text": "Ja",   "callback_data": "approval_ja"},
                            {"text": "Nein", "callback_data": "approval_nein"},
                        ]]
                    } if needs_approval else None

                    # Response-Blöcke senden
                    if response_blocks:
                        blocks_to_send = [b for b in response_blocks if b.get("type") in ("text", "image")]
                        for i, block in enumerate(blocks_to_send):
                            is_last = (i == len(blocks_to_send) - 1) and not (is_voice_input and not needs_approval)
                            if block.get("type") == "text":
                                content = block.get("content", "").strip()
                                if content:
                                    chunks = _split_message(content, 4000)
                                    for j, chunk in enumerate(chunks):
                                        markup = approval_keyboard if (is_last and j == len(chunks) - 1) else None
                                        try:
                                            html = _md_to_html(chunk)
                                            payload = {"chat_id": chat_id, "text": html, "parse_mode": "HTML"}
                                            if markup: payload["reply_markup"] = markup
                                            await http.post(_api_url(token, "sendMessage"), json=payload)
                                        except Exception:
                                            payload = {"chat_id": chat_id, "text": chunk}
                                            if markup: payload["reply_markup"] = markup
                                            await http.post(_api_url(token, "sendMessage"), json=payload)
                            elif block.get("type") == "image":
                                url = block.get("url", "")
                                if url:
                                    await _send_photo(chat_id, url)
                        # Voice-Antwort am Ende — nach allen Text/Bild-Blöcken
                        if is_voice_input and response.strip() and not needs_approval:
                            await _send_voice_reply(chat_id, response)
                    elif is_voice_input and response.strip() and not needs_approval:
                        sent = await _send_voice_reply(chat_id, response)
                        if not sent:
                            await _send(chat_id, response)
                    else:
                        chunks = _split_message(response or "…", 4000)
                        for j, chunk in enumerate(chunks):
                            markup = approval_keyboard if (j == len(chunks) - 1 and approval_keyboard) else None
                            try:
                                html = _md_to_html(chunk)
                                payload = {"chat_id": chat_id, "text": html, "parse_mode": "HTML"}
                                if markup: payload["reply_markup"] = markup
                                r2 = await http.post(_api_url(token, "sendMessage"), json=payload)
                                if not r2.is_success:
                                    payload2 = {"chat_id": chat_id, "text": chunk}
                                    if markup: payload2["reply_markup"] = markup
                                    await http.post(_api_url(token, "sendMessage"), json=payload2)
                            except Exception:
                                try:
                                    payload2 = {"chat_id": chat_id, "text": chunk}
                                    if markup: payload2["reply_markup"] = markup
                                    await http.post(_api_url(token, "sendMessage"), json=payload2)
                                except Exception:
                                    pass

            except Exception as e:
                err_msg = str(e)
                # Event-Loop wurde heruntergefahren → Worker sauber beenden, nicht wiederholen
                if "shutdown" in err_msg or "futures after" in err_msg or "closed" in err_msg:
                    print("[Telegram] Event-Loop beendet — Worker beendet sich sauber.")
                    return
                # Timeout/Connect-Fehler → still retry
                t_name = type(e).__name__
                if "Timeout" not in t_name and "Connect" not in t_name:
                    print(f"[Telegram] Worker Fehler: {e}")
                try:
                    await asyncio.sleep(5)
                except Exception:
                    return  # Wenn sleep selbst fehlschlägt, Event-Loop weg → beenden


def _start_polling(token: str):
    with _polling_lock:
        # Thread-Check über enumerate() — überlebt Module-Reloads (modulare Flags werden zurückgesetzt)
        for t in threading.enumerate():
            if t.name == "telegram-polling" and t.is_alive():
                print("[Telegram] Polling-Thread läuft bereits — kein zweiter Start.")
                return

        def _run():
            asyncio.run(_telegram_worker(token))

        t = threading.Thread(target=_run, daemon=True, name="telegram-polling")
        t.start()


# ── Plugin-Registrierung ──────────────────────────────────────────────────────

def register(api):
    api.register_tool(
        name="send_telegram_message",
        description=(
            "Sendet eine Nachricht an den Nutzer via Telegram (an die konfigurierte Chat-ID). "
            "Nutze dies, um dem Nutzer proaktiv Nachrichten zu schicken."
        ),
        func=send_telegram_message,
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Text der Nachricht (Markdown unterstützt)"}
            },
            "required": ["message"],
        },
    )

    token = _get_token()
    if token:
        _start_polling(token)
        print(f"[Plugin] telegram_bot geladen — Chat-ID: {_get_chat_id() or 'unbekannt'}")
    else:
        print("[Plugin] telegram_bot: TELEGRAM_BOT_TOKEN fehlt — Polling deaktiviert.")
