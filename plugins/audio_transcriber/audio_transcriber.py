"""
AION Plugin: audio_transcriber
===============================
Transcribes audio files via Faster Whisper (offline, multilingual).

No manual model download needed — model is downloaded automatically on first use.
Cached in ~/.cache/huggingface/hub/ (default HuggingFace cache).

Setup:
  pip install faster-whisper

Models (configurable via config.json "whisper_model"):
  tiny    — fastest, lowest quality  (~75 MB)
  base    — fast, decent quality     (~145 MB)
  small   — best balance (default)   (~465 MB)
  medium  — better quality           (~1.5 GB)
  large-v3— best quality             (~3 GB)

Config:
  aion config set whisper_model small   (default)
  aion config set whisper_model medium  (better accuracy)
"""

import json
import os
from pathlib import Path

_PLUGIN_DIR  = Path(__file__).parent
_AION_DIR    = _PLUGIN_DIR.parent.parent
_CONFIG_FILE = _AION_DIR / "config.json"

# Lazy-loaded Faster Whisper model
_whisper_model = None


def _get_model_size() -> str:
    """Read whisper_model from config.json. Default: 'small'."""
    try:
        if _CONFIG_FILE.is_file():
            cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            return cfg.get("whisper_model", "small")
    except Exception:
        pass
    return "small"


def _get_model():
    """Lazy-load WhisperModel. Uses CUDA if available, else CPU int8."""
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError(
                "faster-whisper not installed — run: pip install faster-whisper"
            )
        model_size = _get_model_size()
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
            f"[audio_transcriber] Loading Whisper '{model_size}' "
            f"on {device} ({compute_type})…",
            flush=True,
        )
        _whisper_model = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _whisper_model


def transcribe_audio(file_path: str, language: str = "") -> str:
    """Transcribes any audio file via Faster Whisper (offline, multilingual).

    Supports WAV, MP3, OGG, M4A, FLAC, WebM and all formats ffmpeg can decode.
    Auto-detects language when language is empty.
    Returns the transcribed text as a plain string.
    """
    if not os.path.exists(file_path):
        return f"ERROR: Audio file not found: {file_path}"
    try:
        model = _get_model()
        kwargs = {"beam_size": 5}
        if language:
            kwargs["language"] = language
        segments, _info = model.transcribe(str(file_path), **kwargs)
        return " ".join(seg.text.strip() for seg in segments).strip()
    except Exception as e:
        return f"ERROR during transcription: {e}"


def register(api):
    api.register_tool(
        name="transcribe_audio",
        description=(
            "Transcribes an audio file (WAV, MP3, OGG, M4A, FLAC, ...) to text "
            "via Faster Whisper (fully offline, multilingual, no model download needed). "
            "Auto-detects language. Returns transcribed text as string."
        ),
        func=transcribe_audio,
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Full path to the audio file",
                },
                "language": {
                    "type": "string",
                    "description": "Language code (e.g. 'de', 'en', 'fr'). Empty = auto-detect.",
                },
            },
            "required": ["file_path"],
        },
    )
