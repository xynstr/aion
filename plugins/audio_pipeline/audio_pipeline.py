"""
AION Plugin: audio_pipeline
============================
Universelles Audio-Ein/Ausgabe-Plugin für AION.

Stellt zwei Tools bereit:
  - audio_transcribe_any : Beliebige Audiodatei → Text (ffmpeg + Vosk, offline)
  - audio_tts            : Text → WAV-Sprachdatei (multi-engine Router)

TTS-Engines (steuerbar via engine-Parameter oder config.json "tts_engine"):
  - sapi5  : Windows SAPI5 via pyttsx3 (offline, roboterhaft) — Fallback
  - edge   : Microsoft Neural TTS via edge-tts (online, sehr natürlich, kostenlos)
             Stimme konfigurierbar via config.json "tts_voice" (z.B. "de-DE-KatjaNeural")
  - piper  : Piper TTS (offline, neural, schnell) — in Vorbereitung

Engine-Priorität:
  1. Expliziter engine-Parameter beim Aufruf
  2. config.json → "tts_engine"
  3. Fallback: "sapi5"

Andere Plugins (Telegram, WhatsApp, Discord, ...) können dieses Plugin direkt
importieren — keine API-Keys, keine Cloud-Abhängigkeiten.

Benötigt:
  - ffmpeg im PATH  (winget install Gyan.FFmpeg)
  - pyttsx3         (pip install pyttsx3)           — für engine=sapi5
  - edge-tts        (pip install edge-tts)          — für engine=edge
  - vosk            (pip install vosk)              — für Transkription
  - Vosk-Modell unter plugins/audio_transcriber/vosk-model-small-de-0.15/
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

_PLUGIN_DIR = Path(__file__).parent
_AION_DIR   = _PLUGIN_DIR.parent.parent
_MODEL_PATH = _AION_DIR / "plugins" / "audio_transcriber" / "vosk-model-small-de-0.15"
_CONFIG_FILE = _AION_DIR / "config.json"

# Lazy-geladenes Vosk-Modell (wird nur einmal geladen)
_vosk_model = None


# ── Config-Helfer ─────────────────────────────────────────────────────────────

def _get_tts_config() -> tuple[str, str]:
    """Liest tts_engine + tts_voice aus config.json. Fallback: sapi5 / de-DE-KatjaNeural."""
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
    """Gibt den Pfad zur ffmpeg-Binary zurück oder None wenn nicht gefunden."""
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
    """Konvertiert beliebige Audiodatei → WAV (mono, 16 kHz, 16-bit) via ffmpeg.
    Gibt den Pfad zur temporären WAV-Datei zurück.
    Caller ist für das Löschen der Datei zuständig.
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
        "-ar", "16000",       # 16 kHz Abtastrate (optimal für Vosk)
        "-ac", "1",           # Mono
        "-sample_fmt", "s16", # 16-bit PCM
        tmp.name,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode != 0:
        os.unlink(tmp.name)
        raise RuntimeError(
            f"ffmpeg Fehler (exit {result.returncode}): "
            f"{result.stderr.decode(errors='replace')[:400]}"
        )
    return tmp.name


def _transcribe_wav(wav_path: str) -> str:
    """Transkribiert eine WAV-Datei via Vosk. Gibt erkannten Text zurück."""
    global _vosk_model
    try:
        from vosk import Model, KaldiRecognizer
        import wave
    except ImportError:
        raise RuntimeError("vosk nicht installiert: pip install vosk")

    if not _MODEL_PATH.exists():
        raise RuntimeError(
            f"Vosk-Modell nicht gefunden: {_MODEL_PATH}\n"
            "Bitte herunterladen von https://alphacephei.com/vosk/models "
            "und als plugins/audio_transcriber/vosk-model-small-de-0.15/ entpacken."
        )

    if _vosk_model is None:
        _vosk_model = Model(str(_MODEL_PATH))

    with wave.open(wav_path, "rb") as wf:
        rec = KaldiRecognizer(_vosk_model, wf.getframerate())
        rec.SetWords(True)
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            rec.AcceptWaveform(data)

    return json.loads(rec.FinalResult()).get("text", "")


# ── Öffentliche Tool-Funktionen ───────────────────────────────────────────────

def audio_transcribe_any(file_path: str) -> dict:
    """Transkribiert beliebige Audiodateien (ogg, mp3, m4a, wav, ...) in Text.

    Kann direkt von anderen Plugins importiert werden:
        from audio_pipeline.audio_pipeline import audio_transcribe_any
        result = audio_transcribe_any("/tmp/voice.ogg")
        # → {"ok": True, "text": "hallo welt", "converted": True}
    """
    input_path = str(file_path)

    if not os.path.exists(input_path):
        return {"ok": False, "error": f"Datei nicht gefunden: {input_path}"}

    wav_path = None
    try:
        # Direkt-Versuch für WAV (spart ffmpeg-Aufruf)
        if input_path.lower().endswith(".wav"):
            try:
                text = _transcribe_wav(input_path)
                return {"ok": True, "text": text, "converted": False}
            except Exception:
                pass  # Fallback: über ffmpeg konvertieren

        # Konvertierung via ffmpeg → temporäre WAV → Vosk
        wav_path = _convert_to_wav(input_path)
        text = _transcribe_wav(wav_path)
        return {"ok": True, "text": text, "converted": True}

    except Exception as e:
        return {"ok": False, "error": str(e)}

    finally:
        if wav_path and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except Exception:
                pass


def _tts_sapi5(text: str, output_path: str) -> dict:
    """TTS via pyttsx3 / Windows SAPI5 (offline, Fallback)."""
    try:
        import pyttsx3
    except ImportError:
        return {"ok": False, "error": "pyttsx3 nicht installiert: pip install pyttsx3"}
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
            return {"ok": False, "error": "SAPI5 erzeugte leere Datei"}
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
        return {"ok": False, "error": "edge-tts nicht installiert: pip install edge-tts"}

    # edge-tts speichert nativ als MP3 — wir nutzen .mp3 als Output
    mp3_path = output_path.replace(".wav", ".mp3") if output_path.endswith(".wav") else output_path + ".mp3"
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
            return {"ok": False, "error": "edge-tts erzeugte leere Datei"}
        return {"ok": True, "path": mp3_path, "engine": "edge", "voice": voice, "format": "mp3"}
    except Exception as e:
        return {"ok": False, "error": f"edge-tts Fehler: {e}"}


def audio_tts(text: str, engine: str = "", output_path: str = "") -> dict:
    """Wandelt Text in gesprochene Sprache um — multi-engine Router.

    engine: "edge" (Microsoft Neural, online, empfohlen) |
            "sapi5" (offline, Fallback) |
            "" → liest aus config.json "tts_engine"

    Konfiguration via config.json:
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
            "Wandelt beliebige Audiodateien (ogg, mp3, m4a, wav, ...) in Text um. "
            "Nutzt ffmpeg für Formatkonvertierung und Vosk für Offline-Spracherkennung (Deutsch). "
            "Gibt {ok, text} zurück."
        ),
        func=audio_transcribe_any,
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Vollständiger Pfad zur Audiodatei",
                }
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
                    "description": "Optionaler Ausgabepfad. Leer = temporäre Datei.",
                },
            },
            "required": ["text"],
        },
    )
