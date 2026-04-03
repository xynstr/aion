# DOCX to Speech

Liest Word-Dokumente (`.docx`) vor und speichert sie als MP3- oder WAV-Audiodatei.

## Voraussetzungen

- **Audio Pipeline Plugin** muss in AION aktiv sein (liefert die TTS-Engine)
- `python-docx` wird automatisch installiert

## Tool: `docx_to_speech`

| Parameter | Typ | Pflicht | Beschreibung |
|-----------|-----|---------|--------------|
| `docx_path` | string | ✅ | Pfad zur `.docx`-Datei |
| `output_path` | string | — | Ausgabepfad für die Audiodatei. Leer = automatisch neben der Quelldatei |
| `engine` | string | — | `edge` (online, MP3) oder `sapi5` (offline, WAV). Leer = aus `config.json` |

### Rückgabe

```json
{
  "ok": true,
  "path": "C:/Dokumente/Bericht.mp3",
  "engine": "edge",
  "voice": "de-DE-KatjaNeural",
  "format": "mp3",
  "source": "C:/Dokumente/Bericht.docx",
  "chars": 3842
}
```

## Beispiele

**Einfach vorlesen:**
> „Lies die Datei `C:/Dokumente/Bericht.docx` vor."

**Mit Ausgabepfad:**
> „Konvertiere `Vertrag.docx` zu `Vertrag.mp3`."

**Offline (kein Internet):**
> „Lies `Notizen.docx` vor, nutze sapi5."

## TTS-Konfiguration

Die Stimme und Engine können in `config.json` festgelegt werden:

```json
{
  "tts_engine": "edge",
  "tts_voice": "de-DE-KatjaNeural"
}
```

Verfügbare deutsche Stimmen (edge):
- `de-DE-KatjaNeural` — weiblich (Standard)
- `de-DE-ConradNeural` — männlich
- `de-AT-IngridNeural` — österreichisch
- `de-CH-LeniNeural` — schweizerdeutsch

## Abhängigkeiten

| Paket | Zweck |
|-------|-------|
| `python-docx` | Text aus `.docx` extrahieren |
| `edge-tts` *(via Audio Pipeline)* | Microsoft Neural TTS → MP3 |
| `pyttsx3` *(via Audio Pipeline)* | Windows SAPI5 → WAV (Offline-Fallback) |
