"""
AION Plugin: Discord Bot
=========================
Bidirektionaler Discord-Bot mit per-User-Sessions.
Antwortet auf @Mentions und Direktnachrichten.

Konfiguration (.env):
    DISCORD_BOT_TOKEN=your_bot_token

Einrichtung:
  1. https://discord.com/developers/applications → Neue App → Bot
  2. Bot-Token kopieren → DISCORD_BOT_TOKEN=...
  3. Unter "Privileged Gateway Intents": MESSAGE CONTENT INTENT aktivieren
  4. Bot einladen: OAuth2 → URL Generator → bot + application.commands → Scope
     → Permissions: Send Messages, Read Message History, Use Slash Commands

Abhängigkeit:
    pip install discord.py
"""

import asyncio
import os
import threading
from pathlib import Path

try:
    import discord
    from discord.ext import commands
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False

_bot_started = False
_start_lock  = threading.Lock()
_sessions: dict[int, object] = {}   # user_id -> AionSession
_busy:     set[int]          = set()


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _split_message(text: str, max_len: int = 1900) -> list[str]:
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


def _get_session(user_id: int) -> object:
    """Gibt eine AionSession für den User zurück (erstellt bei Bedarf)."""
    from aion import AionSession
    if user_id not in _sessions:
        _sessions[user_id] = AionSession(channel=f"discord_{user_id}")
    return _sessions[user_id]


# ── Bot-Logik ──────────────────────────────────────────────────────────────────

def _create_bot() -> "commands.Bot":
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"[Discord] Bot online als {bot.user} (ID: {bot.user.id})")
        try:
            synced = await bot.tree.sync()
            print(f"[Discord] {len(synced)} Slash-Commands synchronisiert.")
        except Exception as e:
            print(f"[Discord] Slash-Command-Sync fehlgeschlagen: {e}")

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        is_dm      = isinstance(message.channel, discord.DMChannel)
        is_mention = bot.user in message.mentions

        if not is_dm and not is_mention:
            return

        user_id = message.author.id

        if user_id in _busy:
            await message.channel.send("Ich verarbeite noch deine letzte Nachricht, bitte warte kurz...")
            return

        # @Mentions aus dem Text entfernen
        text = message.content
        for mention in message.mentions:
            text = text.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        text = text.strip()

        # Bilder verarbeiten
        images = []
        for attachment in message.attachments:
            ct = attachment.content_type or ""
            if ct.startswith("image/"):
                images.append(attachment.url)

        # Nicht-Bild-Anhänge: Fehlermeldung
        for attachment in message.attachments:
            ct = attachment.content_type or ""
            if not ct.startswith("image/"):
                try:
                    from aion import unsupported_file_message
                    msg = unsupported_file_message(f"«{attachment.filename}» ({ct or 'unbekannt'})")
                except Exception:
                    msg = f"Dateityp «{attachment.filename}» kann ich leider nicht direkt verarbeiten."
                await message.channel.send(msg)
                return

        if not text and not images:
            return

        _busy.add(user_id)
        sess = _get_session(user_id)

        async with message.channel.typing():
            try:
                reply = await sess.turn(text or "Was siehst du auf diesem Bild?",
                                        images=images if images else None)
            except Exception as e:
                reply = f"Fehler: {e}"
            finally:
                _busy.discard(user_id)

        for chunk in _split_message(str(reply)):
            await message.channel.send(chunk)

        # Bilder aus dem letzten AION-Response-Block senden
        try:
            for block in getattr(sess, "_last_response_blocks", []):
                if isinstance(block, dict) and block.get("type") == "image":
                    url = block.get("url") or block.get("image", "")
                    if url and url.startswith("http"):
                        await message.channel.send(url)
        except Exception:
            pass

    # ── Slash-Command /ask ───────────────────────────────────────────────────

    @bot.tree.command(name="ask", description="Stelle AION eine Frage")
    async def ask_command(interaction: discord.Interaction, frage: str):
        await interaction.response.defer()
        user_id = interaction.user.id
        sess    = _get_session(user_id)
        try:
            reply = await sess.turn(frage)
        except Exception as e:
            reply = f"Fehler: {e}"
        for chunk in _split_message(str(reply)):
            await interaction.followup.send(chunk)

    return bot


def _start_bot_thread(token: str):
    global _bot_started
    with _start_lock:
        if _bot_started:
            return
        _bot_started = True

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bot = _create_bot()
        try:
            loop.run_until_complete(bot.start(token))
        except Exception as e:
            print(f"[Discord] Bot-Thread beendet: {e}")

    t = threading.Thread(target=_run, daemon=True, name="discord-bot")
    t.start()
    print("[Discord] Bot-Thread gestartet.")


# ── Register ───────────────────────────────────────────────────────────────────

def register(api):
    if not HAS_DISCORD:
        print("[discord_bot] 'discord.py' nicht installiert.")
        print("  Bitte ausführen: pip install discord.py")
        return

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("[discord_bot] DISCORD_BOT_TOKEN nicht gesetzt — Plugin deaktiviert.")
        return

    _start_bot_thread(token)
    print("[discord_bot] ✓ Discord-Bot gestartet.")
