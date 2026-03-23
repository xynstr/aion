# Plugin: clio_reflection

**CLIO reflection cycle for structured thinking**

## Funktion

Implementiert die CLIO-Methode (Confidence, Logic, Information, Outcome) zur Konfidenz-Bewertung. AION analysiert seine Sicherheit bei Aufgaben und entscheidet, ob er weitere Recherche braucht oder direkt antworten kann.

## Tool: `clio_check`

**Parameter:**
- `nutzerfrage` (string): Die aktuelle Aufgabe
- `last_response` (string, optional): If AION already answered, for verification
- `force` (boolean, optional): Zyklus erzwingen

**Ausgabe:**
- `konfidenz`: 0-100, wie sicher AION ist
- `clio`: Solution approach + reasoning
- `meta`: Meta-Check und kritische Annahmen
- `next`: Weiter mit continue_work oder direkt answer?

## Funktionsweise

1. Ansatz formulieren
2. Konfidenz bewerten (40-95%)
3. Explain reasoning
4. Meta-check: Which assumptions could be wrong?

Wenn Konfidenz < 70% → AION recherchiert mehr. Wenn ≥ 70% → antwortet direkt.
