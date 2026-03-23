"""
AION Plugin: Discord Bot
=========================
Bidirektionaler Discord-Bot mit per-User-Sessions.
Antwortet auf @Mentions und Direktnachrichten.

Configuration (.env):
    DISCORD_BOT_TOKEN=your_bot_token

Setup:
  1. https://discord.com/developers/applications → Neue App → Bot
  2. Bot-Token kopieren → DISCORD_BOT_TOKEN=...
  3. Unter "Privileged Gateway Intents": MESSAGE CONTENT INTENT aktivieren
  4. Bot einladen: OAuth2 → URL Generator → bot + application.commands → Scope
     → Permissions: Send Messages, Read Message History, Use Slash Commands

Dependency:
    pip install discord.py
"""

import asyncio
import importlib.util
import io
import os
import tempfile
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

# ── audio_pipeline Lazy-Import ────────────────────────────────────────────────

_audio_pipeline_mod = None

def _get_audio_pipeline():
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
        print(f"[Discord] audio_pipeline nicht ladbar: {e}")
        return None


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
    """Returns eine AionSession für den User zurück (erstellt bei Bedarf)."""
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

    async def _send_image(channel, url: str):
        """Sendet ein Bild: data:-URL als File-Upload, HTTP-URL als Text."""
        if url.startswith("data:"):
            import base64 as _b64
            header, b64data = url.split(",", 1)
            mime = header.split(":")[1].split(";")[0]
            ext = ".jpg" if "jpeg" in mime else ".png"
            img_bytes = _b64.b64decode(b64data)
            await channel.send(file=discord.File(fp=io.BytesIO(img_bytes), filename=f"screenshot{ext}"))
        elif url.startswith("http"):
            await channel.send(url)

    async def _send_voice_reply(channel, text_reply: str) -> bool:
        """Generiert TTS-Audio und sendet es als Discord-Audiodatei."""
        ap = _get_audio_pipeline()
        if not ap:
            return False
        wav_tmp = None
        try:
            loop = asyncio.get_event_loop()
            tts_res = await loop.run_in_executor(None, ap.audio_tts, text_reply)
            if not tts_res.get("ok"):
                print(f"[Discord] TTS Error: {tts_res.get('error')}")
                return False
            wav_tmp = tts_res["path"]
            with open(wav_tmp, "rb") as f:
                audio_bytes = f.read()
            ext = ".mp3" if tts_res.get("format") == "mp3" else ".wav"
            await channel.send(file=discord.File(fp=io.BytesIO(audio_bytes), filename=f"voice{ext}"))
            return True
        except Exception as e:
            print(f"[Discord] Voice-Reply Error: {e}")
            return False
        finally:
            if wav_tmp and os.path.exists(wav_tmp):
                try:
                    os.unlink(wav_tmp)
                except Exception:
                    pass

    async def _stream_and_send(channel, sess, text: str, images=None, is_voice_input: bool = False):
        """Streamt AionSession und sendet Text + Bilder an Discord-Channel."""
        response = ""
        response_blocks = []
        try:
            async for event in sess.stream(text, images=images):
                t = event.get("type")
                if t == "done":
                    response = event.get("full_response", response)
                    response_blocks = event.get("response_blocks", [])
                elif t == "token":
                    response += event.get("content", "")
                elif t == "error":
                    response = f"Error: {event.get('message', '?')}"
        except Exception as e:
            response = f"Error: {e}"
            print(f"[Discord] stream() Error: {e}")

        if response_blocks:
            for block in response_blocks:
                if block.get("type") == "text":
                    for chunk in _split_message(block.get("content", "").strip()):
                        if chunk:
                            await channel.send(chunk)
                elif block.get("type") == "image":
                    url = block.get("url", "")
                    if url:
                        try:
                            await _send_image(channel, url)
                        except Exception as img_e:
                            print(f"[Discord] Bild senden fehlgeschlagen: {img_e}")
        elif is_voice_input and response.strip():
            sent = await _send_voice_reply(channel, response)
            if not sent:
                for chunk in _split_message(response or "…"):
                    await channel.send(chunk)
        else:
            for chunk in _split_message(response or "…"):
                await channel.send(chunk)

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
            await message.channel.send("Ich verarbeite noch deine letzte Nachricht, bitte warten...")
            return

        # @Mentions aus dem Text entfernen
        text = message.content
        for mention in message.mentions:
            text = text.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        text = text.strip()

        # Anhänge klassifizieren
        images = []
        voice_attachment = None
        for attachment in message.attachments:
            ct = attachment.content_type or ""
            if ct.startswith("image/"):
                images.append(attachment.url)
            elif ct.startswith("audio/"):
                voice_attachment = attachment
            else:
                # Nicht unterstützter Filetyp
                try:
                    from aion import unsupported_file_message
                    msg = unsupported_file_message(f"«{attachment.filename}» ({ct or 'unbekannt'})")
                except Exception:
                    msg = f"Filetyp «{attachment.filename}» kann ich leider nicht direkt verarbeiten."
                await message.channel.send(msg)
                return

        # Voice-Nachricht transkribieren
        is_voice_input = False
        if voice_attachment and not text:
            try:
                audio_bytes = await voice_attachment.read()
                ct = voice_attachment.content_type or ""
                ext = ".ogg" if "ogg" in ct else ".mp3" if "mp3" in ct else ".m4a"
                tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                tmp.write(audio_bytes)
                tmp.close()
                ap = _get_audio_pipeline()
                if ap:
                    loop = asyncio.get_event_loop()
                    res = await loop.run_in_executor(None, ap.audio_transcribe_any, tmp.name)
                    if res.get("ok") and res.get("text", "").strip():
                        text = res["text"].strip()
                        is_voice_input = True
                        print(f"[Discord] Sprachnachricht -> '{text[:70]}'")
                    else:
                        text = f"[Sprachnachricht — Transkription fehlgeschlagen: {res.get('error', '?')}]"
                os.unlink(tmp.name)
            except Exception as e:
                print(f"[Discord] Voice-Transkription fehlgeschlagen: {e}")

        if not text and not images:
            return

        _busy.add(user_id)
        sess = _get_session(user_id)

        async with message.channel.typing():
            try:
                await _stream_and_send(
                    message.channel, sess,
                    text or "Was siehst du auf diesem Bild?",
                    images=images if images else None,
                    is_voice_input=is_voice_input,
                )
            finally:
                _busy.discard(user_id)

    # ── Slash-Command /ask ───────────────────────────────────────────────────

    @bot.tree.command(name="ask", description="Stelle AION eine Frage")
    async def ask_command(interaction: discord.Interaction, frage: str):
        await interaction.response.defer()
        user_id = interaction.user.id
        sess    = _get_session(user_id)
        response = ""
        response_blocks = []
        try:
            async for event in sess.stream(frage):
                t = event.get("type")
                if t == "done":
                    response = event.get("full_response", response)
                    response_blocks = event.get("response_blocks", [])
                elif t == "token":
                    response += event.get("content", "")
                elif t == "error":
                    response = f"Error: {event.get('message', '?')}"
        except Exception as e:
            response = f"Error: {e}"
        if response_blocks:
            for block in response_blocks:
                if block.get("type") == "text":
                    for chunk in _split_message(block.get("content", "").strip()):
                        if chunk:
                            await interaction.followup.send(chunk)
                elif block.get("type") == "image":
                    url = block.get("url", "")
                    if url:
                        try:
                            if url.startswith("data:"):
                                import base64 as _b64
                                header, b64data = url.split(",", 1)
                                mime = header.split(":")[1].split(";")[0]
                                ext = ".jpg" if "jpeg" in mime else ".png"
                                img_bytes = _b64.b64decode(b64data)
                                await interaction.followup.send(
                                    file=discord.File(fp=io.BytesIO(img_bytes), filename=f"screenshot{ext}")
                                )
                            elif url.startswith("http"):
                                await interaction.followup.send(url)
                        except Exception as img_e:
                            print(f"[Discord] /ask Bild senden fehlgeschlagen: {img_e}")
        else:
            for chunk in _split_message(response or "…"):
                await interaction.followup.send(chunk)

    return bot


def _start_bot_thread(token: str):
    with _start_lock:
        for t in threading.enumerate():
            if t.name == "discord-bot" and t.is_alive():
                print("[Discord] Bot-Thread läuft bereits — kein zweiter Start.")
                return

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
        print("[discord_bot] 'discord.py' not installed.")
        print("  Please run: pip install discord.py")
        return

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("[discord_bot] DISCORD_BOT_TOKEN nicht gesetzt — Plugin deaktiviert.")
        return

    _start_bot_thread(token)
    print("[discord_bot] Discord-Bot gestartet.")
