# Shell Tools

Führt Shell-Befehle und Package-Installation cross-platform aus.

## Features

- **Cross-Platform**: Windows (winget), macOS (brew), Linux (apt-get/snap)
- **Memory-Tracking**: Erfolgreiche Installs werden in `aion_memory.json` protokolliert
- **Error-Handling**: Detaillierte Fehlerausgaben bei Fehlschlag
- **Permission-Check**: Warnt vor erhöhten Privilegien

## Tools

| Tool | Beschreibung |
|------|-------------|
| `shell_exec(command)` | Führt Shell-Befehl aus (bash/PowerShell/zsh) |
| `system_install(software)` | Installiert Software (winget/brew/apt-get) |
| `install_package(package, package_manager)` | Installiert Paket via pip/npm/cargo/etc. |

## Verwendung

Sag zu AION:
- *"Installiere ffmpeg"* — automatische Erkennung der Plattform
- *"Führe aus: git status"* — direkte Shell-Kommandos
- *"Installiere das npm-Paket express"*

## Sicherheit

⚠️ Diese Tools erfordern User-Bestätigung bevor sie ausgeführt werden:
- Neue Software-Installation
- Paket-Manager-Aufrufe
- Unbekannte Shell-Befehle

## Plattform-Support

| OS | Package Manager | Shell |
|----|-----------------|-------|
| Windows | winget | PowerShell / CMD |
| macOS | brew | bash / zsh |
| Linux | apt-get, snap | bash |

## Memory

Erfolgreiche Installs werden mit Datum und Ergebnis in `aion_memory.json` gespeichert.
