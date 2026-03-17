# Plugin: restart_tool

**AION Neustart und Cache-Bereinigung**

## Funktion

Ermöglicht AION, sich selbst neuzustarten. Nützlich nach Code-Änderungen (z.B. via `self_patch_code` an `aion.py`) um sicherzustellen, dass neue Logik wirksam wird.

## Tool: `self_restart`

**Parameter:** keine

**Effekt:**
- Löscht alle `__pycache__` Verzeichnisse
- Startet neuen AION-Prozess
- Beendet aktuellen Prozess

## Funktionsweise

1. Findet alle `__pycache__`-Dirs rekursiv
2. Löscht sie um veraltete .pyc-Dateien zu entfernen
3. Startet `aion.py` in separaten Prozess (neue Console)
4. Beendet aktuellen Prozess mit `sys.exit(0)`

## Wann notwendig?

- Nach Änderungen an `aion.py` (via `self_patch_code`)
- Nach Installation neuer Packages
- Um Cache-Probleme zu beheben
- Um ein "sauberes" Python-Environment zu erzwingen

## Beispiel

```
AION ändert aion.py via self_patch_code
→ AION ruft self_restart auf
→ Neue Instanz startet mit geändertem Code
→ Alte Instanz beendet sich
```

## Hinweis

Nach einem Neustart müssen Sie ggf. neu im Web UI http://localhost:7000 connecten.
