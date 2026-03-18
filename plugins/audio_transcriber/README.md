# audio_transcriber

Transkribiert WAV-Audiodateien in Text via Vosk (offline, Deutsch).

## Zweck

Basismodul für Spracherkennung. Verarbeitet ausschließlich WAV-Dateien (mono, 16-bit PCM, 16 kHz). Für alle anderen Formate (ogg, mp3, m4a, ...) das `audio_pipeline`-Plugin verwenden, das intern auf dieses Vosk-Modell zurückgreift.

## Tools

- `transcribe_audio(file_path)` — Transkribiert eine WAV-Datei und gibt den erkannten Text als String zurück. Gibt eine Fehlermeldung zurück wenn das Format nicht stimmt oder das Modell fehlt.

## Abhängigkeiten

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

Für universelle Audio-Unterstützung das `audio_pipeline`-Plugin nutzen — es übernimmt Konvertierung und ruft `transcribe_audio` intern auf.
