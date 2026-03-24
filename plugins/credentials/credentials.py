"""
AION Plugin: Credentials Vault
================================
Sicherer lokaler Speicher für Zugangsdaten, API-Keys und Passwörter.

Verschlüsselung: Fernet (AES-128-CBC + HMAC-SHA256)
Speicherort:     credentials/{dienst}.md.enc  (vollständig gitignoriert)
Schlüssel:       credentials/.vault.key        (gitignoriert, niemals teilen)

Jeder Dienst bekommt eine eigene Markdown-Datei:
  credentials/facebook.md.enc   → Facebook Login
  credentials/openai.md.enc     → OpenAI API Key
  credentials/telegram.md.enc   → Telegram Bot Token

Tools:
  credential_write(service, content)  → speichert + verschlüsselt
  credential_read(service)            → liest + entschlüsselt
  credential_list()                   → listet alle Dienste
  credential_delete(service)          → löscht einen Eintrag
"""

import os
import re
from pathlib import Path

import aion as _aion_module

VAULT_DIR = Path(__file__).parent.parent.parent / "credentials"
KEY_FILE  = VAULT_DIR / ".vault.key"


# ── Schlüssel-Management ───────────────────────────────────────────────────────

def _get_fernet():
    """Lädt oder generiert den Vault-Schlüssel und gibt eine Fernet-Instanz zurück."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError(
            "Paket 'cryptography' fehlt. Bitte installieren: pip install cryptography"
        )
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        key = KEY_FILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        KEY_FILE.chmod(0o600)  # Nur Owner darf lesen
    return Fernet(key)


def _service_to_filename(service: str) -> str:
    """Normalisiert den Dienstnamen zu einem sicheren Dateinamen."""
    name = service.lower().strip()
    name = re.sub(r"[^\w\-]", "_", name)   # Nur Buchstaben, Zahlen, - und _
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "unnamed"


def _credential_path(service: str) -> Path:
    return VAULT_DIR / f"{_service_to_filename(service)}.md.enc"


# ── Tool-Implementierungen ─────────────────────────────────────────────────────

async def _credential_write(service: str, content: str) -> str:
    """Speichert Zugangsdaten für einen Dienst verschlüsselt im Vault.

    service: Name des Dienstes (z.B. "facebook", "openai", "telegram")
    content: Markdown-Inhalt mit Zugangsdaten (z.B. "## Facebook\n- E-Mail: ...\n- Passwort: ...")
    """
    if not service or not service.strip():
        return '{"error": "Kein Dienstname angegeben"}'
    if not content or not content.strip():
        return '{"error": "Kein Inhalt angegeben"}'

    try:
        f    = _get_fernet()
        data = content.encode("utf-8")
        enc  = f.encrypt(data)
        path = _credential_path(service)
        path.write_bytes(enc)
        return f'{{"ok": true, "service": "{_service_to_filename(service)}", "path": "{path.name}"}}'
    except Exception as e:
        return f'{{"error": "{e}"}}'


async def _credential_read(service: str) -> str:
    """Liest und entschlüsselt Zugangsdaten für einen Dienst aus dem Vault.

    service: Name des Dienstes
    """
    if not service or not service.strip():
        return '{"error": "Kein Dienstname angegeben"}'

    path = _credential_path(service)
    if not path.exists():
        # Fuzzy-Suche: ähnlich klingende Dienste vorschlagen
        available = [p.stem.replace(".md", "") for p in VAULT_DIR.glob("*.md.enc")]
        hint = f", verfügbar: {', '.join(available)}" if available else " (Vault ist leer)"
        return f'{{"error": "Keine Credentials für \'{service}\' gefunden{hint}"}}'

    try:
        f    = _get_fernet()
        enc  = path.read_bytes()
        data = f.decrypt(enc).decode("utf-8")
        # JSON-sichere Ausgabe
        import json
        return json.dumps({"ok": True, "service": _service_to_filename(service), "content": data})
    except Exception as e:
        return f'{{"error": "Entschlüsselung fehlgeschlagen: {e}"}}'


async def _credential_list() -> str:
    """Listet alle gespeicherten Dienste im Vault auf (ohne Inhalt)."""
    try:
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(VAULT_DIR.glob("*.md.enc"))
        services = [p.stem.replace(".md", "") for p in files]
        import json
        return json.dumps({
            "ok":       True,
            "count":    len(services),
            "services": services,
            "vault":    str(VAULT_DIR),
        })
    except Exception as e:
        return f'{{"error": "{e}"}}'


async def _credential_delete(service: str) -> str:
    """Löscht die Credentials eines Dienstes dauerhaft aus dem Vault.

    service: Name des Dienstes
    """
    if not service or not service.strip():
        return '{"error": "Kein Dienstname angegeben"}'

    path = _credential_path(service)
    if not path.exists():
        return f'{{"error": "Keine Credentials für \'{service}\' gefunden"}}'

    try:
        path.unlink()
        return f'{{"ok": true, "deleted": "{path.name}"}}'
    except Exception as e:
        return f'{{"error": "{e}"}}'


# ── Plugin-Registrierung ───────────────────────────────────────────────────────

def register(api):
    api.register_tool(
        name="credential_write",
        description=(
            "Speichert Zugangsdaten, API-Keys oder Passwörter für einen Dienst sicher "
            "und verschlüsselt im lokalen Credentials-Vault. Jeder Dienst bekommt eine "
            "eigene Markdown-Datei (z.B. 'facebook', 'openai', 'telegram'). "
            "Der Inhalt wird AES-verschlüsselt und ist komplett gitignoriert."
        ),
        func=_credential_write,
        input_schema={
            "type": "object",
            "properties": {
                "service": {
                    "type":        "string",
                    "description": "Name des Dienstes, z.B. 'facebook', 'openai', 'telegram', 'server_ssh'",
                },
                "content": {
                    "type":        "string",
                    "description": (
                        "Markdown-Text mit den Zugangsdaten. Beispiel:\n"
                        "## Facebook\n- E-Mail: user@example.com\n- Passwort: geheim\n"
                        "- Wiederherstellungscode: ABC-123"
                    ),
                },
            },
            "required": ["service", "content"],
        },
    )

    api.register_tool(
        name="credential_read",
        description=(
            "Liest und entschlüsselt gespeicherte Zugangsdaten für einen Dienst aus dem "
            "lokalen Credentials-Vault. Gibt den Markdown-Inhalt zurück."
        ),
        func=_credential_read,
        input_schema={
            "type": "object",
            "properties": {
                "service": {
                    "type":        "string",
                    "description": "Name des Dienstes, z.B. 'facebook', 'openai'",
                },
            },
            "required": ["service"],
        },
    )

    api.register_tool(
        name="credential_list",
        description=(
            "Listet alle im lokalen Credentials-Vault gespeicherten Dienste auf. "
            "Zeigt nur Dienstnamen, keinen verschlüsselten Inhalt."
        ),
        func=_credential_list,
        input_schema={
            "type":       "object",
            "properties": {},
        },
    )

    api.register_tool(
        name="credential_delete",
        description=(
            "Löscht die Credentials eines Dienstes dauerhaft aus dem Vault. "
            "Diese Aktion kann nicht rückgängig gemacht werden."
        ),
        func=_credential_delete,
        input_schema={
            "type": "object",
            "properties": {
                "service": {
                    "type":        "string",
                    "description": "Name des Dienstes dessen Credentials gelöscht werden sollen",
                },
            },
            "required": ["service"],
        },
    )

    print("[Plugin] credentials loaded — Vault:", VAULT_DIR)
