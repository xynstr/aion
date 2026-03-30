# audio_pipeline

Universal audio input/output plugin. Transcribes any audio to text and generates speech — fully offline, no cloud dependency.

## Purpose

Central audio infrastructure for AION. Other plugins (Telegram, Discord, ...) import this directly to process voice messages or generate audio output.

## Tools

- `audio_transcribe_any(file_path, language?)` — Converts any audio file (OGG, MP3, M4A, WAV, FLAC, WebM, ...) to text via **Faster Whisper** (offline, multilingual). Returns `{ok, text}`.
- `audio_tts(text, engine?, output_path?)` — Converts text to spoken audio. Returns `{ok, path, engine}`.

## STT (Speech-to-Text)

Uses **Faster Whisper** — fully offline, multilingual, auto-detects language.
- No manual model download — downloaded automatically on first use
- Model configurable via `aion config set whisper_model small|medium|large-v3`
- ffmpeg recommended for non-WAV formats (optional)

## TTS (Text-to-Speech)

| Engine | Quality | Requires |
|--------|---------|---------|
| `edge` | ⭐⭐⭐ Microsoft Neural (online) | `pip install edge-tts` |
| `sapi5` | ⭐⭐ Windows built-in (offline) | `pip install pyttsx3` |

Configure engine and voice:
```bash
aion config set tts_engine edge
aion config set tts_voice de-DE-KatjaNeural
```

## Dependencies

| Package | Purpose | Installation |
|---------|---------|-------------|
| `faster-whisper` | Speech recognition | `pip install faster-whisper` |
| `pyttsx3` | TTS fallback (offline) | `pip install pyttsx3` |
| `edge-tts` | TTS best quality (online) | `pip install edge-tts` |
| `ffmpeg` (optional) | Non-WAV audio formats | `winget install Gyan.FFmpeg` |

## Usage by Other Plugins

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
result = ap.audio_transcribe_any("/tmp/voice.ogg")  # → {"ok": True, "text": "hello world"}
result = ap.audio_tts("Hello World")                # → {"ok": True, "path": "/tmp/xyz.mp3"}
```

## File Structure

```
plugins/audio_pipeline/
  audio_pipeline.py   ← this plugin
  README.md
```
