"""
AION Plugin: audio_pipeline
============================
Universal audio input/output plugin for AION.

Tools:
  - audio_transcribe_any : Any audio file → text (Faster Whisper, fully offline)
  - audio_tts            : Text → spoken audio (multi-engine router)

STT (Speech-to-Text):
  - Faster Whisper (offline, multilingual, auto-detects language)
  - No manual model download — auto-downloaded on first use (~465 MB for 'small')
  - Model size configurable via: aion config set whisper_model small|medium|large-v3
  - ffmpeg recommended for non-WAV formats (optional — WAV always works without it)

TTS engines (via engine parameter or config.json "tts_engine"):
  - edge   : Microsoft Neural TTS (online, best quality)  — recommended
             Voice: config.json "tts_voice" (e.g. "de-DE-KatjaNeural")
  - sapi5  : Windows SAPI5 via pyttsx3 (offline, fallback)
  - piper  : Piper TTS (offline, neural) — planned

Engine priority:
  1. Explicit engine= parameter
  2. config.json → "tts_engine"
  3. Fallback: "sapi5"

Other plugins (Telegram, Discord, ...) can import this directly — no API keys needed.

Requirements:
  - faster-whisper  (pip install faster-whisper)   — for transcription
  - pyttsx3         (pip install pyttsx3)           — for engine=sapi5
  - edge-tts        (pip install edge-tts)          — for engine=edge
  - ffmpeg (optional, winget install Gyan.FFmpeg)   — for non-WAV audio formats
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ── Pfade ────────────────────────────────────────────────────────────────────

_PLUGIN_DIR  = Path(__file__).parent
_AION_DIR    = _PLUGIN_DIR.parent.parent
_CONFIG_FILE = _AION_DIR / "config.json"

# Lazy-loaded Faster Whisper model (shared with audio_transcriber plugin)
_whisper_model = None


# ── Config-Helfer ─────────────────────────────────────────────────────────────

def _get_tts_config() -> tuple[str, str]:
    """Reads tts_engine + tts_voice aus config.json. Fallback: sapi5 / de-DE-KatjaNeural."""
    try:
        if _CONFIG_FILE.exists():
            cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            engine = cfg.get("tts_engine", "sapi5")
            voice  = cfg.get("tts_voice",  "de-DE-KatjaNeural")
            return engine, voice
    except Exception:
        pass
    return "sapi5", "de-DE-KatjaNeural"


# ── Interne Helfer ───────────────────────────────────────────────────────────

def _find_ffmpeg() -> str | None:
    """Returns den Pfad zur ffmpeg-Binary zurück oder None wenn nicht gefunden."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    # WinGet-Fallback: Gyan.FFmpeg installiert in AppData\Local\Microsoft\WinGet\Packages
    import glob, os
    winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    matches = glob.glob(os.path.join(winget_base, "Gyan.FFmpeg*", "**", "ffmpeg.exe"), recursive=True)
    if matches:
        return matches[0]
    return None

def _ffmpeg_ok() -> bool:
    return _find_ffmpeg() is not None


def _convert_to_wav(input_path: str) -> str:
    """Converts any audio file → WAV (mono, 16 kHz, 16-bit) via ffmpeg.
    Returns path to a temporary WAV file. Caller must delete it.
    Used for TTS output conversion only — transcription goes directly to Whisper.
    """
    ffmpeg_bin = _find_ffmpeg()
    if not ffmpeg_bin:
        if sys.platform == "win32":
            hint = "winget install Gyan.FFmpeg"
        elif sys.platform == "darwin":
            hint = "brew install ffmpeg"
        else:
            hint = "sudo apt-get install ffmpeg"
        raise RuntimeError(f"ffmpeg not found. Install it with: {hint}")
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [
        ffmpeg_bin, "-y", "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        "-sample_fmt", "s16",
        tmp.name,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode != 0:
        os.unlink(tmp.name)
        raise RuntimeError(
            f"ffmpeg error (exit {result.returncode}): "
            f"{result.stderr.decode(errors='replace')[:400]}"
        )
    return tmp.name


def _get_whisper_model_size() -> str:
    """Read whisper_model from config.json. Default: 'small'."""
    try:
        if _CONFIG_FILE.is_file():
            cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            return cfg.get("whisper_model", "small")
    except Exception:
        pass
    return "small"


def _get_whisper_model():
    """Lazy-load Faster Whisper model. Shares instance with audio_transcriber plugin."""
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError(
                "faster-whisper not installed — run: pip install faster-whisper"
            )
        model_size = _get_whisper_model_size()
        device = "cpu"
        compute_type = "int8"
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
        except ImportError:
            pass
        print(
            f"[audio_pipeline] Loading Whisper '{model_size}' "
            f"on {device} ({compute_type})…",
            flush=True,
        )
        _whisper_model = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _whisper_model


def _transcribe_with_whisper(audio_path: str, language: str = "") -> str:
    """Transcribes any audio file via Faster Whisper. Returns plain text."""
    model = _get_whisper_model()
    kwargs = {"beam_size": 5}
    if language:
        kwargs["language"] = language
    segments, _info = model.transcribe(audio_path, **kwargs)
    return " ".join(seg.text.strip() for seg in segments).strip()


# ── Öffentliche Tool-Functionen ───────────────────────────────────────────────

def audio_transcribe_any(file_path: str, language: str = "") -> dict:
    """Transcribes any audio file (OGG, MP3, M4A, WAV, FLAC, WebM, ...) to text.

    Uses Faster Whisper (fully offline, multilingual). Auto-detects language.
    Faster Whisper uses ffmpeg internally for non-WAV formats when available.

    Can be imported directly by other plugins:
        from audio_pipeline.audio_pipeline import audio_transcribe_any
        result = audio_transcribe_any("/tmp/voice.ogg")
        # → {"ok": True, "text": "hello world", "language": "en"}
    """
    input_path = str(file_path)

    if not os.path.exists(input_path):
        return {"ok": False, "error": f"File not found: {input_path}"}

    try:
        text = _transcribe_with_whisper(input_path, language=language)
        return {"ok": True, "text": text}

    except RuntimeError as e:
        err = str(e)
        # If Whisper fails on non-WAV due to missing ffmpeg, try converting first
        if "ffmpeg" in err.lower() or "audio" in err.lower():
            wav_path = None
            try:
                wav_path = _convert_to_wav(input_path)
                text = _transcribe_with_whisper(wav_path, language=language)
                return {"ok": True, "text": text}
            except Exception as e2:
                return {"ok": False, "error": str(e2)}
            finally:
                if wav_path and os.path.exists(wav_path):
                    try:
                        os.unlink(wav_path)
                    except Exception:
                        pass
        return {"ok": False, "error": err}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tts_sapi5(text: str, output_path: str) -> dict:
    """TTS via pyttsx3 / Windows SAPI5 (offline, Fallback)."""
    try:
        import pyttsx3
    except ImportError:
        return {"ok": False, "error": "pyttsx3 not installed: pip install pyttsx3"}
    try:
        eng = pyttsx3.init()
        for v in eng.getProperty("voices"):
            vid  = (v.id   or "").lower()
            vnam = (v.name or "").lower()
            if "de" in vid or "german" in vid or "deutsch" in vnam or "hedda" in vnam:
                eng.setProperty("voice", v.id)
                break
        eng.setProperty("rate", 155)
        eng.setProperty("volume", 1.0)
        eng.save_to_file(text, output_path)
        eng.runAndWait()
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return {"ok": False, "error": "SAPI5 erzeugte leere File"}
        return {"ok": True, "path": output_path, "engine": "sapi5", "format": "wav"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tts_edge(text: str, output_path: str, voice: str = "de-DE-KatjaNeural") -> dict:
    """TTS via edge-tts (Microsoft Neural, online, kostenlos).

    Stimmen (Auswahl Deutsch):
      de-DE-KatjaNeural    — weiblich, natürlich (Standard)
      de-DE-ConradNeural   — männlich
      de-AT-IngridNeural   — österreichisch, weiblich
      de-CH-LeniNeural     — schweizerdeutsch, weiblich
    """
    try:
        import edge_tts
    except ImportError:
        return {"ok": False, "error": "edge-tts not installed: pip install edge-tts"}

    # edge-tts speichert nativ als MP3 — wir nutzen .mp3 als Output
    if output_path.endswith(".mp3"):
        mp3_path = output_path
    elif output_path.endswith(".wav"):
        mp3_path = output_path.replace(".wav", ".mp3")
    else:
        mp3_path = output_path + ".mp3"
    try:
        async def _run():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(mp3_path)

        # Laufenden Event-Loop wiederverwenden falls vorhanden (z.B. in FastAPI)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _run())
                    future.result(timeout=30)
            else:
                loop.run_until_complete(_run())
        except RuntimeError:
            asyncio.run(_run())

        if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
            return {"ok": False, "error": "edge-tts erzeugte leere File"}
        return {"ok": True, "path": mp3_path, "engine": "edge", "voice": voice, "format": "mp3"}
    except Exception as e:
        return {"ok": False, "error": f"edge-tts Error: {e}"}


def audio_tts(text: str, engine: str = "", output_path: str = "") -> dict:
    """Wandelt Text in gesprochene Sprache um — multi-engine Router.

    engine: "edge" (Microsoft Neural, online, empfohlen) |
            "sapi5" (offline, Fallback) |
            "" → liest aus config.json "tts_engine"

    Configuration via config.json:
        {"tts_engine": "edge", "tts_voice": "de-DE-KatjaNeural"}

    Kann direkt von anderen Plugins importiert werden:
        from audio_pipeline.audio_pipeline import audio_tts
        result = audio_tts("Hallo Welt")
    """
    cfg_engine, cfg_voice = _get_tts_config()
    active_engine = engine or cfg_engine

    if not output_path:
        suffix = ".mp3" if active_engine == "edge" else ".wav"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.close()
        output_path = tmp.name

    if active_engine == "edge":
        result = _tts_edge(text, output_path, voice=cfg_voice)
        if not result.get("ok"):
            # Fallback auf sapi5 wenn edge fehlschlägt (kein Internet etc.)
            print(f"[audio_tts] edge-tts fehlgeschlagen ({result.get('error')}) — Fallback sapi5")
            wav_path = output_path.replace(".mp3", ".wav") if output_path.endswith(".mp3") else output_path
            return _tts_sapi5(text, wav_path)
        return result

    return _tts_sapi5(text, output_path)


# ── Plugin-Registrierung ─────────────────────────────────────────────────────

def register(api):
    api.register_tool(
        name="audio_transcribe_any",
        description=(
            "Transcribes any audio file (OGG, MP3, M4A, WAV, FLAC, WebM, ...) to text. "
            "Uses Faster Whisper (fully offline, multilingual, auto-detects language). "
            "Returns {ok, text}."
        ),
        func=audio_transcribe_any,
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Full path to the audio file",
                },
                "language": {
                    "type": "string",
                    "description": "Language code (e.g. 'de', 'en'). Empty = auto-detect.",
                },
            },
            "required": ["file_path"],
        },
    )

    api.register_tool(
        name="audio_tts",
        description=(
            "Wandelt Text in gesprochene Sprache um — multi-engine Router. "
            "Standard-Engine aus config.json (tts_engine). "
            "Engines: 'edge' (Microsoft Neural, online, beste Qualität), 'sapi5' (offline, Fallback). "
            "Gibt {ok, path, engine} zurück."
        ),
        func=audio_tts,
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text der gesprochen werden soll",
                },
                "engine": {
                    "type": "string",
                    "description": "TTS-Engine: 'edge' (empfohlen, online) oder 'sapi5' (offline). Leer = aus config.json.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optionaler Ausgabepfad. Leer = temporäre File.",
                },
            },
            "required": ["text"],
        },
    )
