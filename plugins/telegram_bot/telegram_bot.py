"""
AION Plugin: Telegram Bot (bidirektional)
=========================================
- Empfängt Nachrichten vom Nutzer via Telegram → leitet sie an AION weiter
- AION kann Nachrichten an Telegram senden (Tool: send_telegram_message)

Konfiguration (.env):
  TELEGRAM_BOT_TOKEN=1234567890:AAEXAMPLE...
  TELEGRAM_CHAT_ID=123456789   (optional, wird beim ersten /start automatisch gespeichert)

Installation:
  pip install python-telegram-bot requests
"""

import asyncio
import os
import threading
import json
from pathlib import Path

# Token aus Env-Var lesen (primär), Datei als Fallback
_TOKEN_FILE   = Path.home() / ".aion_telegram_token"
_CHATID_FILE  = Path.home() / ".aion_telegram_chatid"

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


# ── Nachricht senden (via requests — kein Event-Loop benötigt) ─────────────────

def send_telegram_message(params) -> dict:
    """Sendet eine Nachricht an die konfigurierte Telegram-Chat-ID."""
    message = params.get("message", "") if isinstance(params, dict) else str(params)
    token = _get_token()
    cid   = _get_chat_id()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN nicht gesetzt (weder in .env noch in ~/.aion_telegram_token)"}
    if not cid:
        return {"ok": False, "error": "Keine Chat-ID bekannt. Sende /start an den Bot um sie zu registrieren."}
    try:
        import requests as _req
        r = _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": cid, "text": message},
            timeout=10,
        )
        r.raise_for_status()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Polling-Bot (empfängt Nachrichten) ────────────────────────────────────────

def _start_polling(token: str):
    """Startet den Telegram-Bot-Polling-Loop in einem eigenen Thread."""

    try:
        from telegram import Update
        from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
    except ImportError:
        print("[Telegram] python-telegram-bot nicht installiert. Polling deaktiviert.")
        print("[Telegram] Installieren mit: pip install python-telegram-bot")
        return

    # run_aion_turn wird erst beim ersten Aufruf importiert (lazy), um Zirkularimporte zu vermeiden
    def _get_run_aion():
        try:
            from aion import run_aion_turn
            return run_aion_turn
        except ImportError:
            return None

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        cid = str(update.effective_chat.id)
        _save_chat_id(cid)
        await update.message.reply_text(
            "✅ AION Telegram-Bot aktiviert!\n"
            f"Chat-ID gespeichert: {cid}\n"
            "Du kannst jetzt Nachrichten an AION senden."
        )

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        _save_chat_id(str(update.effective_chat.id))
        user_text   = update.message.text
        run_aion    = _get_run_aion()

        if run_aion is None:
            await update.message.reply_text("Fehler: AION-Kernlogik nicht erreichbar.")
            return

        try:
            # run_aion_turn ist synchron und nutzt intern asyncio.run() —
            # in asyncio.to_thread laufen wir in einem separaten Thread ohne laufende Loop
            response = await asyncio.to_thread(run_aion, user_text, "telegram")
        except Exception as e:
            response = f"Fehler bei der Verarbeitung: {e}"

        # Telegram-Nachrichten max. 4096 Zeichen
        if len(response) > 4000:
            response = response[:4000] + "\n… (Antwort gekürzt)"
        await update.message.reply_text(response)

    def _run():
        app = ApplicationBuilder().token(token).build()
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        print("[Telegram] Bot-Polling gestartet.")
        app.run_polling(stop_signals=None)

    t = threading.Thread(target=_run, daemon=True, name="TelegramBotThread")
    t.start()


# ── Plugin-Registrierung ──────────────────────────────────────────────────────

def register(api):
    api.register_tool(
        name="send_telegram_message",
        description=(
            "Sendet eine Nachricht an den Nutzer via Telegram. "
            "Erfordert TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID in .env."
        ),
        func=send_telegram_message,
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Die zu sendende Nachricht"}
            },
            "required": ["message"],
        },
    )

    token = _get_token()
    if token:
        _start_polling(token)
        cid = _get_chat_id()
        status = f"Chat-ID: {cid}" if cid else "Chat-ID: noch unbekannt (sende /start an den Bot)"
        print(f"[Plugin] telegram_bot geladen — {status}")
    else:
        print("[Plugin] telegram_bot geladen — WARNUNG: TELEGRAM_BOT_TOKEN nicht gesetzt, Polling deaktiviert.")
        print("         Setze TELEGRAM_BOT_TOKEN in .env um den Bot zu aktivieren.")
