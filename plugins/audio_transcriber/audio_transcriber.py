"""
AION Plugin: audio_transcriber
===============================
Transkribiert WAV-Fileen (mono, 16-bit PCM) via Vosk (Offline).

Für universelle Audio-Unterstützung (ogg, mp3, m4a, ...):
→ Nutze das audio_pipeline-Plugin, das dieses Plugin intern verwendet.
"""

import json
import os
from pathlib import Path

_MODEL_PATH = Path(__file__).parent / "vosk-model-small-de-0.15"

# Globales Vosk-Modell (lazy load)
vosk_model = None


def transcribe_audio(file_path: str) -> str:
    """Transkribiert eine WAV-File (mono, 16-bit) mit Vosk."""
    global vosk_model

    if not _MODEL_PATH.exists():
        return (
            f"FEHLER: Vosk-Modell nicht gefunden unter {_MODEL_PATH}. "
            "Bitte von https://alphacephei.com/vosk/models herunterladen und entpacken."
        )

    if not os.path.exists(file_path):
        return f"FEHLER: Audiodatei nicht gefunden: {file_path}"

    try:
        from vosk import Model, KaldiRecognizer
        import wave

        if vosk_model is None:
            vosk_model = Model(str(_MODEL_PATH))

        with wave.open(file_path, "rb") as wf:
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
                return "FEHLER: WAV-File muss mono und 16-bit PCM sein. Nutze audio_transcribe_any für andere Formate."

            rec = KaldiRecognizer(vosk_model, wf.getframerate())
            rec.SetWords(True)
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                rec.AcceptWaveform(data)

        return json.loads(rec.FinalResult()).get("text", "")

    except Exception as e:
        return f"FEHLER bei der Transkription: {e}"


def register(api):
    api.register_tool(
        name="transcribe_audio",
        description=(
            "Transkribiert eine WAV-Audiodatei (mono, 16-bit PCM) in Text via Vosk (offline). "
            "Für andere Formate (ogg, mp3, m4a) nutze audio_transcribe_any."
        ),
        func=transcribe_audio,
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Vollständiger Pfad zur .wav-Audiodatei",
                }
            },
            "required": ["file_path"],
        },
    )
