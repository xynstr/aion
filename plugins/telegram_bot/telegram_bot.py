"""
AION Plugin: Telegram Bot (bidirektional)
=========================================
Nutzt AionSession — vollständige Feature-Parität mit dem Web UI:
  - Eigene Konversations-History pro Telegram-User
  - Memory-Injection, Thoughts-Injection
  - Automatischer Charakter-Update alle 5 Gespräche
  - Lange Antworten werden automatisch aufgeteilt

Konfiguration (.env):
  TELEGRAM_BOT_TOKEN=1234567890:AAEXAMPLE...
  TELEGRAM_CHAT_ID=123456789   (optional, wird beim ersten /start gespeichert)

Abhängigkeit:
  pip install httpx
"""

import asyncio
import os
import threading
from pathlib import Path

_TOKEN_FILE  = Path.home() / ".aion_telegram_token"
_CHATID_FILE = Path.home() / ".aion_telegram_chatid"
_polling_lock = threading.Lock()
_polling_started = False


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


# ── Tool: Nachricht senden (sync, für AION-Tool-Dispatch) ────────────────────

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
                    # Versuch 1: Mit MarkdownV2
                    r = http.post(_api_url(token, "sendMessage"),
                                  json={"chat_id": cid, "text": chunk, "parse_mode": "MarkdownV2"})
                    # Fallback auf reinen Text
                    if not r.is_success and "can't parse" in r.text.lower():
                        http.post(_api_url(token, "sendMessage"),
                                  json={"chat_id": cid, "text": chunk})
                except Exception:
                    # Fallback bei generischem Fehler
                    http.post(_api_url(token, "sendMessage"),
                              json={"chat_id": cid, "text": chunk})
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Async Worker: eigener Event-Loop im Daemon-Thread ─────────────────────────

async def _telegram_worker(token: str):
    """Vollständig asynchroner Long-Polling Worker.

    Läuft in einem eigenen Event-Loop (via asyncio.run im Daemon-Thread).
    Jeder Telegram-User bekommt seine eigene AionSession — inkl. History,
    Memory, Charakter-Update usw.
    """
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

    sessions: dict = {}  # chat_id (str) → AionSession
    offset = 0
    print("[Telegram] Async Long-Polling Worker gestartet.")

    async with httpx.AsyncClient(timeout=35.0) as http:

        async def _send(chat_id: str, text: str):
            for chunk in _split_message(text, 4000):
                try:
                    # Versuch 1: Mit MarkdownV2 senden
                    r = await http.post(
                        _api_url(token, "sendMessage"),
                        json={
                            "chat_id": chat_id,
                            "text": chunk,
                            "parse_mode": "MarkdownV2",
                        },
                    )
                    # Wenn das fehlschlägt (z.B. wegen Syntax), als reinen Text senden
                    if not r.is_success and "can't parse" in r.text.lower():
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

        async def _send_images(chat_id: str, image_urls: list):
            """Sendet Bilder via Telegram sendPhoto API."""
            for url in image_urls:
                try:
                    await http.post(
                        _api_url(token, "sendPhoto"),
                        json={"chat_id": chat_id, "photo": url},
                    )
                except Exception as e:
                    print(f"[Telegram] Fehler beim Senden von Bild {url}: {e}")

        while True:
            try:
                r = await http.get(
                    _api_url(token, "getUpdates"),
                    params={"offset": offset, "timeout": 8},
                )

                if not r.is_success:
                    if r.status_code == 409:
                        # 409 = alte Instanz noch aktiv (Long-Poll läuft noch)
                        # Warte > 8s damit der alte Poll-Timeout abläuft
                        print(f"[Telegram] getUpdates HTTP 409 — warte 10s auf alten Poll-Timeout...")
                        await asyncio.sleep(10)
                    else:
                        print(f"[Telegram] getUpdates HTTP {r.status_code} — Retry in 5s")
                        await asyncio.sleep(5)
                    continue

                data = r.json()
                if not data.get("ok"):
                    print(f"[Telegram] API-Fehler: {data.get('description', data)}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset  = update["update_id"] + 1
                    msg     = update.get("message", {})
                    text    = (msg.get("text") or msg.get("caption") or "").strip()
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    photos  = msg.get("photo", [])

                    if not chat_id or (not text and not photos):
                        continue

                    _save_chat_id(chat_id)

                    if text.startswith("/start"):
                        await _send(chat_id,
                            "✅ AION Telegram-Bot aktiviert!\n"
                            f"Chat-ID: {chat_id}\n"
                            "Schreib mir einfach — du kannst auch Bilder senden!")
                        continue

                    # Session pro User — erstmalig History laden
                    if chat_id not in sessions:
                        sess = AionSession(channel=f"telegram_{chat_id}")
                        await sess.load_history(num_entries=10)
                        sessions[chat_id] = sess

                    # Bild(er) als Base64-Data-URL laden wenn vorhanden
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

                    # Typing-Keepalive: sendet alle 4s "typing" während KI arbeitet
                    async def _typing_keepalive():
                        while True:
                            try:
                                await http.post(_api_url(token, "sendChatAction"),
                                                json={"chat_id": chat_id, "action": "typing"})
                            except Exception:
                                pass
                            await asyncio.sleep(4)

                    # Stream nutzen damit Typing parallel läuft
                    typing_task     = asyncio.create_task(_typing_keepalive())
                    response        = ""
                    response_blocks = []
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
                            elif t == "error":
                                response = f"Fehler: {event.get('message', '?')}"
                    except Exception as e:
                        response = f"Fehler bei der Verarbeitung: {e}"
                        print(f"[Telegram] stream() Fehler für {chat_id}: {e}")
                    finally:
                        typing_task.cancel()

                    if not response.strip() and not response_blocks:
                        response = "Fertig."

                    # Response-Blöcke rendern: Text → sendMessage, Bild → sendPhoto
                    if response_blocks:
                        for block in response_blocks:
                            if block.get("type") == "text":
                                content = block.get("content", "").strip()
                                if content:
                                    await _send(chat_id, content)
                            elif block.get("type") == "image":
                                url = block.get("url", "")
                                if url:
                                    try:
                                        await http.post(
                                            _api_url(token, "sendPhoto"),
                                            json={"chat_id": chat_id, "photo": url},
                                        )
                                    except Exception as img_e:
                                        print(f"[Telegram] sendPhoto Fehler: {img_e}")
                    else:
                        await _send(chat_id, response or "…")

            except httpx.TimeoutException:
                continue  # Normal — Long-Poll Timeout, sofort neu starten
            except httpx.ConnectError as e:
                print(f"[Telegram] Verbindungsfehler: {e} — Retry in 10s")
                await asyncio.sleep(10)
            except Exception as e:
                print(f"[Telegram] Unerwarteter Fehler: {e} — Retry in 5s")
                await asyncio.sleep(5)


def _start_polling(token: str):
    """Startet den async Worker in einem Daemon-Thread mit eigenem Event-Loop.

    Verhindert mehrfaches Starten durch Lock.
    """
    global _polling_started
    with _polling_lock:
        if _polling_started:
            return
        _polling_started = True

    def _run():
        asyncio.run(_telegram_worker(token))

    t = threading.Thread(target=_run, daemon=True, name="TelegramWorkerThread")
    t.start()


# ── Plugin-Registrierung ──────────────────────────────────────────────────────

def register(api):
    api.register_tool(
        name="send_telegram_message",
        description=(
            "Sendet eine Nachricht an den Nutzer via Telegram. "
            "Erfordert TELEGRAM_BOT_TOKEN in .env. "
            "Lange Nachrichten werden automatisch aufgeteilt."
        ),
        func=send_telegram_message,
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Die zu sendende Nachricht"},
            },
            "required": ["message"],
        },
    )

    token = _get_token()
    if token:
        _start_polling(token)
        cid    = _get_chat_id()
        status = f"Chat-ID: {cid}" if cid else "Chat-ID: noch unbekannt (sende /start)"
        print(f"[Plugin] telegram_bot geladen — {status}")
    else:
        print("[Plugin] telegram_bot geladen — WARNUNG: TELEGRAM_BOT_TOKEN nicht gesetzt.")
        print("         Setze TELEGRAM_BOT_TOKEN in .env um den Bot zu aktivieren.")
