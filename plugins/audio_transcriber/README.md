# audio_transcriber

Transcribes audio files to text via **Faster Whisper** (offline, multilingual).

## Purpose

Base module for speech recognition. Supports all common audio formats (WAV, MP3, OGG, M4A, FLAC, WebM, ...).
No manual model download needed — model is downloaded automatically on first use.

For universal audio support including TTS, use the `audio_pipeline` plugin.

## Tools

- `transcribe_audio(file_path, language?)` — Transcribes any audio file and returns the recognized text as a string. Auto-detects language when `language` is not provided.

## Dependencies

| Package | Installation |
|---------|-------------|
| `faster-whisper` | `pip install faster-whisper` |
| `ffmpeg` (optional) | `winget install Gyan.FFmpeg` — needed for non-WAV formats |

## Model Configuration

Default model: `small` (~465 MB, downloaded automatically on first use).

```bash
aion config set whisper_model small    # default — best balance
aion config set whisper_model medium   # better accuracy
aion config set whisper_model large-v3 # best quality (~3 GB)
aion config set whisper_model base     # faster, lower quality
aion config set whisper_model tiny     # fastest, lowest quality
```

Models are cached in `~/.cache/huggingface/hub/`.

## GPU Support

Automatically uses CUDA if `torch` with CUDA is installed:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

## File Structure

```
plugins/audio_transcriber/
  audio_transcriber.py   ← this plugin
  README.md
```
