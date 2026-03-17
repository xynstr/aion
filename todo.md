# AION TODO & Routinen

- Format:
  - [ ] Aufgabe (offen)
  - [x] Aufgabe (erledigt)
  - [>] Aufgabe (läuft)
  - [@2026-03-18 14:00] Aufgabe (geplant für Termin)
  - [r:08:00] Aufgabe (Routine täglich 08:00)

---

## Offene Aufgaben
- [ ] Beispiel: self_restart Patch prüfen und testen
- [ ] Beispiel: Heartbeat-Plugin implementieren
- [ ] Gedächtnis-Initialisierung beim Start: memory_short.md, memory_mid.md, memory_long.md automatisch laden
- [ ] Kurzzeitgedächtnis: Immer die letzten 50 Nachrichten/Messages speichern und rotieren
- [ ] Gedächtnis-Komprimierung: Ältere Einträge aus memory_short.md komprimiert in memory_mid.md (und später in memory_long.md) übernehmen
- [ ] Heartbeat-Prüfung und ggf. Start des Heartbeat-Plugins bei jedem Start

## Routinen
- [r:08:00] Gedächtnis-Backup erstellen
- [r:12:00] System-Status prüfen

## Geplante Aufgaben
- [@2026-03-18 10:00] Nutzer an anstehenden Patch erinnern

## Laufend
- [>] Heartbeat-Überwachung aktiv halten

## Erledigt
- [x] restart.bat eingeführt und getestet
