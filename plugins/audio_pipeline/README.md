# audio_pipeline

Universal audio input/output plugin. Converts any audio files to text and generates spoken language — completely offline, no cloud dependency.

## Zweck

This plugin is the central audio infrastructure for AION. Other plugins (Telegram, WhatsApp, Discord, ...) import it directly to process voice messages or generate audio output.

## Tools

- `audio_transcribe_any(file_path)` — Converts any audio files (ogg, mp3, m4a, wav, ...) to WAV via ffmpeg and transcribes with Vosk (offline, German). Gibt `{ok, text, converted}` zurück.
- `audio_tts(text, output_path?)` — Converts text to spoken language (WAV file). Uses pyttsx3 with Windows SAPI5, prefers German voice. Gibt `{ok, path}` zurück.

## Dependencyen

| Paket | Zweck | Installation |
|---|---|---|
| `ffmpeg` | Audio-Formatkonvertierung | `winget install Gyan.FFmpeg` |
| `pyttsx3` | Text-to-Speech (offline) | `pip install pyttsx3` |
| `vosk` | Spracherkennung (offline) | `pip install vosk` |

Vosk-Modell: `plugins/audio_transcriber/vosk-model-small-de-0.15/` muss vorhanden sein.

## Nutzung durch andere Plugins

```python
import importlib.util
from pathlib import Path

def _get_audio_pipeline():
    ap_path = Path(__file__).parent.parent / "audio_pipeline" / "audio_pipeline.py"
    spec = importlib.util.spec_from_file_location("audio_pipeline", ap_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

ap = _get_audio_pipeline()
result = ap.audio_transcribe_any("/tmp/voice.ogg")  # → {"ok": True, "text": "hallo welt"}
result = ap.audio_tts("Hallo Welt")                 # → {"ok": True, "path": "/tmp/xyz.wav"}
```

## Filestruktur

```
plugins/audio_pipeline/
  audio_pipeline.py   ← dieses Plugin
  README.md
```
