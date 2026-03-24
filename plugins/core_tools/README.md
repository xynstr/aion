# Core Tools

Grundlegende AION-Tools für Selbstreflektion, Dokumentation und Systeminformationen.

## Features

- **Hot-Reloadable**: Alle Tools sind per `self_reload_tools` aktualisierbar
- **Memory Integration**: Automatische Aufzeichnung von Erkenntnissen
- **Self-Aware**: AION kann auf seine eigene Dokumentation zugreifen

## Tools

| Tool | Beschreibung |
|------|-------------|
| `continue_work()` | Setzt unterbrochene Arbeit fort (Multi-Turn-Konversation) |
| `read_self_doc()` | Liest AION_SELF.md (Selbstdokumentation) |
| `system_info()` | Gibt System- und Umgebungsinformationen |
| `memory_record(category, summary, lesson, success, hint)` | Speichert Erkenntnisse in `aion_memory.json` |

## Memory-Kategorien

Memory-Einträge werden in Kategorien organisiert:

- `bug_fix` — Behobene Fehler und deren Lösungen
- `feature` — Neue Features und deren Implementierung
- `api_endpoint` — API-Verhalten und Endpunkte
- `tool_learning` — Gelernte Tool-Verhaltensweisen
- `user_preference` — Vorlieben des Users
- `system_knowledge` — System- und Architektur-Wissen

## Verwendung

AION nutzt diese Tools automatisch:
- Ruft `read_self_doc()` auf um über sich selbst zu lernen
- Speichert Erkenntnisse via `memory_record()`
- Nutzt `system_info()` um Systemgrenzen zu verstehen
