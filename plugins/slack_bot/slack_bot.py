"""
AION Plugin: Slack Bot
=======================
Bidirektionaler Slack-Bot mit per-User-Sessions via Socket Mode.
Antwortet auf App-Mentions in Kanälen und auf Direktnachrichten.

Konfiguration (.env):
    SLACK_BOT_TOKEN=xoxb-...      # Bot User OAuth Token
    SLACK_APP_TOKEN=xapp-...      # App-Level Token (Socket Mode)

Einrichtung:
  1. https://api.slack.com/apps → Neue App → "From scratch"
  2. Socket Mode aktivieren (App Settings → Socket Mode)
  3. App-Level Token generieren (Scope: connections:write) → SLACK_APP_TOKEN
  4. Bot-Token: OAuth & Permissions → Bot Token Scopes:
       app_mentions:read, chat:write, im:history, im:read, im:write,
       channels:history, files:read
  5. Event Subscriptions → Subscribe to bot events:
       app_mention, message.im
  6. App installieren → Bot User OAuth Token kopieren → SLACK_BOT_TOKEN

Abhängigkeit:
    pip install slack-bolt
"""

import asyncio
import os
import threading

try:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    HAS_SLACK = True
except ImportError:
    HAS_SLACK = False

_bot_started = False
_start_lock  = threading.Lock()
_sessions: dict[str, object] = {}   # channel_key -> AionSession


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _split_message(text: str, max_len: int = 3000) -> list[str]:
    """Splittet Text in Chunks <= max_len (an Absätzen wenn möglich)."""
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


def _get_session(channel_key: str) -> object:
    """Gibt eine AionSession zurück (erstellt bei Bedarf)."""
    from aion import AionSession
    if channel_key not in _sessions:
        _sessions[channel_key] = AionSession(channel=channel_key)
    return _sessions[channel_key]


def _send_reply(client, channel: str, text: str, thread_ts: str = None):
    """Sendet eine Antwort (ggf. aufgeteilt) in einen Slack-Kanal."""
    for chunk in _split_message(str(text)):
        kwargs = {"channel": channel, "text": chunk}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        try:
            client.chat_postMessage(**kwargs)
        except Exception as e:
            print(f"[Slack] Senden fehlgeschlagen: {e}")


def _run_session(channel_key: str, text: str, client, channel: str, thread_ts: str = None):
    """Synchroner Wrapper: führt session.turn() in eigenem Event-Loop aus."""
    sess = _get_session(channel_key)

    async def _inner():
        return await sess.turn(text)

    loop = asyncio.new_event_loop()
    try:
        reply = loop.run_until_complete(_inner())
    except Exception as e:
        reply = f"Fehler: {e}"
    finally:
        loop.close()

    _send_reply(client, channel, reply, thread_ts)


def _start_bot_thread(bot_token: str, app_token: str):
    global _bot_started
    with _start_lock:
        if _bot_started:
            return
        _bot_started = True

    def _run():
        app = App(token=bot_token)

        # ── App-Mention in Kanal ─────────────────────────────────────────────

        @app.event("app_mention")
        def handle_mention(event, client, say):
            user_id    = event.get("user", "unknown")
            channel    = event.get("channel", "")
            thread_ts  = event.get("thread_ts") or event.get("ts")
            text       = event.get("text", "")

            # Bot-Mention aus Text entfernen
            import re
            text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
            if not text:
                text = "Hallo!"

            channel_key = f"slack_{user_id}"
            threading.Thread(
                target=_run_session,
                args=(channel_key, text, client, channel, thread_ts),
                daemon=True,
            ).start()

        # ── Direktnachricht ──────────────────────────────────────────────────

        @app.event("message")
        def handle_dm(event, client):
            # Nur DMs (channel_type = im), keine Bot-Nachrichten
            if event.get("channel_type") != "im":
                return
            if event.get("bot_id") or event.get("subtype"):
                return

            user_id   = event.get("user", "unknown")
            channel   = event.get("channel", "")
            text      = event.get("text", "").strip()

            if not text:
                return

            channel_key = f"slack_{user_id}"
            threading.Thread(
                target=_run_session,
                args=(channel_key, text, client, channel, None),
                daemon=True,
            ).start()

        # ── Socket Mode starten ──────────────────────────────────────────────
        try:
            handler = SocketModeHandler(app, app_token)
            print("[Slack] Bot verbindet via Socket Mode...")
            handler.start()
        except Exception as e:
            print(f"[Slack] Bot-Thread beendet: {e}")

    t = threading.Thread(target=_run, daemon=True, name="slack-bot")
    t.start()
    print("[Slack] Bot-Thread gestartet.")


# ── Register ───────────────────────────────────────────────────────────────────

def register(api):
    if not HAS_SLACK:
        print("[slack_bot] 'slack-bolt' nicht installiert.")
        print("  Bitte ausführen: pip install slack-bolt")
        return

    bot_token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    app_token = os.environ.get("SLACK_APP_TOKEN", "").strip()

    if not bot_token:
        print("[slack_bot] SLACK_BOT_TOKEN nicht gesetzt — Plugin deaktiviert.")
        return
    if not app_token:
        print("[slack_bot] SLACK_APP_TOKEN nicht gesetzt — Plugin deaktiviert.")
        return

    _start_bot_thread(bot_token, app_token)
    print("[slack_bot] ✓ Slack-Bot gestartet.")
