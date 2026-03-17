# Plugin: clio_reflection

**CLIO-Reflexionszyklus für strukturiertes Denken**

## Funktion

Implementiert die CLIO-Methode (Confidence, Logic, Information, Outcome) zur Konfidenz-Bewertung. AION analysiert seine Sicherheit bei Aufgaben und entscheidet, ob er weitere Recherche braucht oder direkt antworten kann.

## Tool: `clio_check`

**Parameter:**
- `nutzerfrage` (string): Die aktuelle Aufgabe
- `letzte_antwort` (string, optional): Falls AION schon antwortete, zur Überprüfung
- `force` (boolean, optional): Zyklus erzwingen

**Ausgabe:**
- `konfidenz`: 0-100, wie sicher AION ist
- `clio`: Lösungsansatz + Begründung
- `meta`: Meta-Check und kritische Annahmen
- `next`: Weiter mit continue_work oder direkt answer?

## Funktionsweise

1. Ansatz formulieren
2. Konfidenz bewerten (40-95%)
3. Begründung erklären
4. Meta-Check: Welche Annahmen könnten falsch sein?

Wenn Konfidenz < 70% → AION recherchiert mehr. Wenn ≥ 70% → antwortet direkt.
