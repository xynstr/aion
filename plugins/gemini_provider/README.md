# Plugin: gemini_provider

**Google Gemini AI-Provider mit Model-Switching**

## Funktion

Integriert Google's Gemini-Modelle als Alternative zu OpenAI. Erlaubt AION, zwischen OpenAI und Gemini zu wechseln, sowie zwischen verschiedenen Gemini-Versionen.

## Tool: `switch_model`

**Parameter:**
- `model` (string): Modellname

**Verfügbare Gemini-Modelle:**
- `gemini-2.5-pro` (beste Qualität)
- `gemini-2.5-flash` (schnell & günstig)
- `gemini-2.5-flash-lite`
- `gemini-2.0-flash`
- `gemini-2.0-flash-lite`
- `gemini-1.5-pro`

**OpenAI-Modelle (auch wählbar):**
- `gpt-4.1`
- `gpt-4o`
- `o3`
- `o4-mini`

## Konfiguration

```env
GEMINI_API_KEY=AIza...
```

Hol dir einen Key von: https://ai.google.dev/

## Funktionsweise

1. Konvertiert OpenAI Tool-Schemas → Gemini Format
2. Nutzt Gemini Function Calling für Tool-Nutzung
3. Modellwechsel wird in `config.json` persistiert
4. Nächster Start nutzt das gespeicherte Modell

## Beispiel

```
/model gemini-2.5-pro
→ Wechselt zu Gemini 2.5 Pro
→ config.json aktualisiert
```
