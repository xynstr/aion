# Multi-Agent Routing

Ermöglicht AION, komplexe Aufgaben an isolierte Sub-Agenten zu delegieren.

## Features

- **Parallelisierung**: Mehrere Unteraufgaben gleichzeitig bearbeiten
- **Isolation**: Jeder Sub-Agent hat separate Konversationshistorie
- **Pooling**: Bestehende Sub-Agenten wiederverwenden
- **Tracking**: Alle aktiven Sessions anzeigen und verwalten

## Tools

| Tool | Beschreibung |
|------|-------------|
| `delegate_to_agent(task, agent_id, model)` | Delegiert Aufgabe an Sub-Agenten |
| `sessions_list()` | Zeigt alle aktiven Sub-Agenten |
| `sessions_send(agent_id, message)` | Sendet Follow-up an Sub-Agenten |
| `sessions_history(agent_id)` | Zeigt Konversation des Sub-Agenten |

## Verwendung

AION nutzt Multi-Agent automatisch bei komplexen Aufgaben:

```
Nutzerfrage: "Recherchiere 3 verschiedene APIs und vergleiche sie"

AION könnte delegieren:
- Sub-Agent A: Recherchiere API 1 (parallel)
- Sub-Agent B: Recherchiere API 2 (parallel)
- Sub-Agent C: Recherchiere API 3 (parallel)

Dann kombiniert AION die Ergebnisse.
```

## Sub-Agent-IDs

Automatisch generierte IDs: `subagent_abc12345`

## Limits

- Max. aktive Sessions: Systemabhängig
- Memory pro Session: Wie Haupt-Session
- Timeout: Wie normale Konversation
