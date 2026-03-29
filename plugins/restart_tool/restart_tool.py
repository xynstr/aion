"""
AION Plugin: restart_with_approval
====================================
Startet den AION-Prozess vollständig neu — aber nur nach Bestätigung durch den User.

Unterschied zu self_restart (Hot-Reload):
  - self_restart = Plugins neu laden, Prozess läuft weiter (kein Datenverlust, sofort)
  - restart_with_approval = Prozess komplett beenden + neu starten

Functioniert in allen Channelsn (Web UI, Telegram, Discord):
  - confirmed=False → gibt approval_required: True zurück
  - Das vorhandene Approval-System (Ja/Nein-Buttons) übernimmt automatisch
  - Nach "ja" ruft AION restart_with_approval(confirmed=True) auf
"""

import os
import sys
import subprocess
from pathlib import Path


def _get_aion_entry_point():
    """Ermittelt den Haupteinstiegspunkt von AION."""
    entry = Path(sys.argv[0]).resolve()
    if entry.exists() and entry.suffix == ".py":
        return entry
    # Fallback: aion_web.py im AION-Stammverzeichnis
    aion_root = Path(__file__).resolve().parent.parent.parent
    for name in ("aion_web.py", "aion.py"):
        candidate = aion_root / name
        if candidate.exists():
            return candidate
    return entry


def restart_with_approval(reason: str = "", confirmed: bool = False, **_) -> dict:
    """Startet AION neu — zeigt zuerst Ja/Nein-Bestätigungsaufforderung."""
    if not confirmed:
        return {
            "approval_required": True,
            "message": (
                "AION-Prozess neu starten?"
                + (f" Grund: {reason}" if reason else "")
            ),
            "preview": (
                "Der aktuelle AION-Prozess wird beendet und automatisch neu gestartet.\n"
                "Alle offenen Verbindungen werden kurz unterbrochen.\n"
                "Plugins und Einstellungen bleiben erhalten.\n\n"
                "→ 'Ja' zum Neustart, 'Nein' zum Abbrechen."
            ),
        }

    # Bestätigt: Neuen Prozess starten und aktuellen beenden
    entry = _get_aion_entry_point()
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                [sys.executable, str(entry)],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            subprocess.Popen([sys.executable, str(entry)])
        # os._exit umgeht Exception-Handler und beendet sofort
        os._exit(0)
    except Exception as e:
        return {"ok": False, "error": f"Neustart fehlgeschlagen: {e}"}


def register(api):
    api.register_tool(
        name="restart_with_approval",
        description=(
            "Full process restart (not hot-reload). Shows a yes/no confirmation to the user first. "
            "Use when the user says 'restart'. For plugin-only updates use self_restart instead."
        ),
        func=restart_with_approval,
        input_schema={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Optionaler Grund für den Neustart",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "false = Bestätigungsaufforderung anzeigen, true = Neustart durchführen",
                },
            },
            "required": [],
        },
    )
