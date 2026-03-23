# audio_transcriber

Transkribiert WAV-Audiodateien in Text via Vosk (offline, Deutsch).

## Zweck

Base module for speech recognition. Processes only WAV files (mono, 16-bit PCM, 16 kHz). For all other formats (ogg, mp3, m4a, ...) use the `audio_pipeline` plugin, which uses this Vosk model internally.

## Tools

- `transcribe_audio(file_path)` — Transcribes a WAV file and returns the recognized text as a string. Gibt eine Fehlermeldung zurück wenn das Format nicht stimmt oder das Modell fehlt.

## Dependencies

| Paket | Installation |
|---|---|
| `vosk` | `pip install vosk` |

Vosk-Modell: `plugins/audio_transcriber/vosk-model-small-de-0.15/` muss vorhanden sein.

Download: https://alphacephei.com/vosk/models → `vosk-model-small-de-0.15.zip` entpacken.

## Dateistruktur

```
plugins/audio_transcriber/
  audio_transcriber.py          ← dieses Plugin
  vosk-model-small-de-0.15/     ← Sprachmodell (nicht im Repo)
  README.md
```

## Hinweis

Use the `audio_pipeline` plugin for universal audio support — es übernimmt Konvertierung und ruft `transcribe_audio` intern auf.
