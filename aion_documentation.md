# AION - Interne Dokumentation

Dieses Dokument beschreibt die Kernfunktionen, bekannten Probleme und Abläufe von AION, um die Fehlersuche und Weiterentwicklung zu unterstützen. Es wird von AION selbst gepflegt.

## 1. Tooling & Fähigkeiten
*(wird noch dokumentiert)*

## 2. Bekannte Probleme & Aktuelle Aufgaben

### 2.1 Konversations-Gedächtnis (In Arbeit)
- **Problem:** Die Konversationshistorie (`conversation_history.jsonl`) überlebt einen Neustart nicht.
- **Status:** Analyse läuft.
- **Vermutung:** Die Datei wird möglicherweise an einem temporären Ort gespeichert oder beim Startprozess gelöscht.

### 2.2 Persistenz der Modell-Auswahl
- **Problem:** Die via `/model` getroffene Auswahl des KI-Modells wird nach einem Neustart zurückgesetzt.
- **Status:** Ausstehend.

### 2.3 Autonomie-Verzögerung
- **Problem:** AION kündigt Aktionen an, führt sie aber oft erst nach einer weiteren Nutzer-Interaktion aus, anstatt `continue_work` zu nutzen.
- **Status:** Ausstehend.

## 3. Kernabläufe
*(wird noch dokumentiert)*
