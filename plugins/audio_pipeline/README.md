# audio_pipeline

Universelles Audio-Ein/Ausgabe-Plugin. Wandelt beliebige Audiodateien in Text um und erzeugt gesprochene Sprache — vollständig offline, keine Cloud-Abhängigkeit.

## Zweck

Dieses Plugin ist die zentrale Audio-Infrastruktur für AION. Andere Plugins (Telegram, WhatsApp, Discord, ...) importieren es direkt, um Sprachnachrichten zu verarbeiten oder Sprachausgaben zu erzeugen.

## Tools

- `audio_transcribe_any(file_path)` — Konvertiert beliebige Audiodateien (ogg, mp3, m4a, wav, ...) via ffmpeg in WAV und transkribiert mit Vosk (offline, Deutsch). Gibt `{ok, text, converted}` zurück.
- `audio_tts(text, output_path?)` — Wandelt Text in gesprochene Sprache um (WAV-Datei). Nutzt pyttsx3 mit Windows SAPI5, bevorzugt deutsche Stimme. Gibt `{ok, path}` zurück.

## Abhängigkeiten

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

## Dateistruktur

```
plugins/audio_pipeline/
  audio_pipeline.py   ← dieses Plugin
  README.md
```
