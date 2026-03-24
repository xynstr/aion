# Credentials Vault

Sicherer lokaler Speicher für Zugangsdaten, API-Keys und Passwörter.

## Features

- **Verschlüsselung**: Fernet (AES-128-CBC + HMAC-SHA256)
- **Speicherort**: `credentials/{dienst}.md.enc` (vollständig gitignoriert)
- **Schlüssel**: `credentials/.vault.key` (wird automatisch generiert, niemals committen)
- **Pro Dienst**: Separate Markdown-Datei

## Tools

| Tool | Beschreibung |
|------|-------------|
| `credential_write(service, content)` | Speichert Zugangsdaten verschlüsselt |
| `credential_read(service)` | Liest und entschlüsselt Zugangsdaten |
| `credential_list()` | Listet alle gespeicherten Dienste |
| `credential_delete(service)` | Löscht einen Eintrag dauerhaft |

## Verwendung

Sag einfach zu AION:
- *"Speichere meine Facebook-Zugangsdaten: E-Mail foo@bar.com, Passwort 1234"*
- *"Was sind meine OpenAI-Credentials?"*
- *"Welche Credentials habe ich gespeichert?"*
- *"Lösche meine Telegram-Credentials"*

## Backup

Mache regelmäßig ein Backup von:
- `credentials/` (alle verschlüsselten Dateien)
- `credentials/.vault.key` (Schlüssel — absolut kritisch!)

Ohne den Schlüssel sind die verschlüsselten Dateien nicht wiederherstellbar.
