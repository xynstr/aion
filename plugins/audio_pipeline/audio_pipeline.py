"""
AION Plugin: audio_pipeline
============================
Universelles Audio-Ein/Ausgabe-Plugin für AION.

Stellt zwei Tools bereit:
  - audio_transcribe_any : Beliebige Audiodatei → Text (ffmpeg + Vosk, offline)
  - audio_tts            : Text → WAV-Sprachdatei (pyttsx3/SAPI5, offline)

Andere Plugins (Telegram, WhatsApp, Discord, ...) können dieses Plugin direkt
importieren — keine API-Keys, keine Cloud-Abhängigkeiten.

Benötigt:
  - ffmpeg im PATH  (winget install Gyan.FFmpeg)
  - pyttsx3         (pip install pyttsx3)
  - vosk            (pip install vosk)
  - Vosk-Modell unter plugins/audio_transcriber/vosk-model-small-de-0.15/
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# ── Pfade ────────────────────────────────────────────────────────────────────

_PLUGIN_DIR = Path(__file__).parent
_AION_DIR   = _PLUGIN_DIR.parent.parent
_MODEL_PATH = _AION_DIR / "plugins" / "audio_transcriber" / "vosk-model-small-de-0.15"

# Lazy-geladenes Vosk-Modell (wird nur einmal geladen)
_vosk_model = None


# ── Interne Helfer ───────────────────────────────────────────────────────────

def _ffmpeg_ok() -> bool:
    return shutil.which("ffmpeg") is not None


def _convert_to_wav(input_path: str) -> str:
    """Konvertiert beliebige Audiodatei → WAV (mono, 16 kHz, 16-bit) via ffmpeg.
    Gibt den Pfad zur temporären WAV-Datei zurück.
    Caller ist für das Löschen der Datei zuständig.
    """
    if not _ffmpeg_ok():
        raise RuntimeError(
            "ffmpeg nicht gefunden. Installiere es mit: winget install Gyan.FFmpeg"
        )
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
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


def audio_tts(text: str, output_path: str = "") -> dict:
    """Wandelt Text in gesprochene Sprache um (WAV, vollständig offline).

    Nutzt pyttsx3 mit Windows SAPI5 (bevorzugt deutsche Stimme).
    Gibt {"ok": True, "path": "/tmp/xyz.wav"} zurück.

    Kann direkt von anderen Plugins importiert werden:
        from audio_pipeline.audio_pipeline import audio_tts
        result = audio_tts("Hallo Welt")
        wav_path = result["path"]
    """
    try:
        import pyttsx3
    except ImportError:
        return {"ok": False, "error": "pyttsx3 nicht installiert: pip install pyttsx3"}

    if not output_path:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        output_path = tmp.name

    try:
        engine = pyttsx3.init()

        # Deutsche Stimme bevorzugen (Windows SAPI5 hat meist mehrere)
        for v in engine.getProperty("voices"):
            vid  = (v.id   or "").lower()
            vnam = (v.name or "").lower()
            if "de" in vid or "german" in vid or "deutsch" in vnam or "hedda" in vnam:
                engine.setProperty("voice", v.id)
                break

        engine.setProperty("rate", 155)   # Wörter pro Minute (normal = 200)
        engine.setProperty("volume", 1.0)
        engine.save_to_file(text, output_path)
        engine.runAndWait()

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return {"ok": False, "error": "TTS erzeugte leere oder fehlende Datei"}

        return {"ok": True, "path": output_path, "format": "wav"}

    except Exception as e:
        return {"ok": False, "error": str(e)}


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
            "Wandelt Text in gesprochene Sprache um — vollständig offline via pyttsx3/SAPI5. "
            "Gibt Pfad zur erzeugten WAV-Datei zurück. "
            "Gibt {ok, path} zurück."
        ),
        func=audio_tts,
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text der gesprochen werden soll",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optionaler Pfad für die WAV-Ausgabedatei. Leer = temporäre Datei.",
                },
            },
            "required": ["text"],
        },
    )
