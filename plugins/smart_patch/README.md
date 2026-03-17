# Plugin: smart_patch

**Intelligentes Code-Patching mit Fuzzy-Matching**

## Funktion

Führt Code-Patches durch mit Toleranz gegenüber Whitespace und kleineren Formatierungsunterschieden. Nutzt `difflib` um den Zielblock auch zu finden wenn Leerzeichen oder Zeilenumbrüche nicht exakt passen.

## Tool: `smart_patch`

**Parameter:**
- `path` (string): Pfad zur Datei
- `old_block` (string): Mehrzeiliger Originalcode (zu ersetzen)
- `new_block` (string): Neuer Codeabschnitt
- `context_lines` (int, optional): Kontextzeilen zum Finden (default: 5)

**Ausgabe:**
- `ok` (boolean): Erfolgreich?
- `patch_applied` (boolean): Wurde Patch angewendet?
- `details` (string): Bericht über was gefunden/geändert wurde

## Funktionsweise

1. **Exakte Suche**: Zielblock nach exaktem Match suchen (mit Whitespace-Toleranz)
2. **Fuzzy-Suche**: Falls nicht gefunden → difflib.SequenceMatcher nutzen
3. **Kontext**: Umgebende Zeilen zur Bestätigung lesen
4. **Backup**: Ursprungsdatei wird gesichert
5. **Patch**: Text-Abschnitt ersetzen und speichern

## Vorteil gegenüber exaktem Replace

- Verträgt unterschiedliche Einrückung
- Funktioniert auch wenn Whitespace leicht variiert
- Findet Code auch wenn Zeilenumbrüche nicht identisch sind

## Beispiel

```python
smart_patch(
  path="app.py",
  old_block="def hello():\n    print('old')",
  new_block="def hello():\n    print('new')"
)
→ Patch erfolgreich auch wenn Einrückung leicht anders war
```
