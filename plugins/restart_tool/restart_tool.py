import os
import sys
import subprocess
import shutil
from pathlib import Path

def self_restart_func(input: dict = None):
    """Startet AION neu: loescht Caches, startet neuen Prozess, beendet aktuellen."""
    
    # Pfad zur Haupt-AION-Datei (angenommen, das Plugin liegt in AION/plugins)
    aion_py_path = Path(__file__).resolve().parent.parent / 'aion.py'
    
    if not aion_py_path.is_file():
        return {'ok': False, 'error': f'aion.py nicht gefunden unter: {aion_py_path}'}
        
    # Cache-Verzeichnisse finden und löschen
    cache_dirs = list(Path(__file__).resolve().parent.parent.glob('**/__pycache__'))
    for cache_dir in cache_dirs:
        try:
            import shutil
            shutil.rmtree(cache_dir)
            print(f"Cache gelöscht: {cache_dir}")
        except Exception as e:
            print(f"Fehler beim Löschen von Cache {cache_dir}: {e}")


def request_restart_approval() -> dict:
    """
    Fragt den Nutzer um Genehmigung, bevor AION neu gestartet wird.
    Gibt {approved: True/False} zurück. Der eigentliche Neustart wird
    nur durchgeführt, wenn der Nutzer explizit zustimmt.
    """
    print("\n⚠️  AION möchte sich neu starten.")
    print("Grund: Code-Änderungen oder Plugin-Updates wurden vorgenommen.")
    try:
        answer = input("Neustart genehmigen? [j/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return {"approved": False, "reason": "Eingabe abgebrochen."}

    if answer in ("j", "ja", "y", "yes"):
        # Genehmigt — führe den Neustart durch
        aion_py = BOT_DIR / "aion.py"
        restart_bat = BOT_DIR / "restart.bat"

        if not aion_py.is_file():
            return {"approved": True, "ok": False, "error": f"aion.py nicht gefunden: {aion_py}"}

        # Cache leeren
        for cache_dir in BOT_DIR.rglob("__pycache__"):
            try:
                shutil.rmtree(cache_dir)
            except Exception:
                pass

        print("✅ Neustart genehmigt. AION startet neu...")
        try:
            if restart_bat.is_file():
                subprocess.Popen([str(restart_bat)], shell=True)
            else:
                subprocess.Popen([sys.executable, str(aion_py)], creationflags=subprocess.CREATE_NEW_CONSOLE)
            sys.exit(0)
        except Exception as e:
            return {"approved": True, "ok": False, "error": str(e)}
    else:
        print("❌ Neustart abgelehnt. AION läuft weiter.")
        return {"approved": False, "reason": "Nutzer hat den Neustart abgelehnt."}


def register(api):
    """
    Registriert request_restart_approval als 'self_restart'.
    Überschreibt das eingebaute self_restart-Tool in aion.py NICHT direkt,
    aber da Plugins nach builtins geladen werden und Duplikate übersprungen werden,
    muss aion.py gepatcht werden (siehe aion.py Fix). Dieses Plugin registriert
    das Tool unter 'restart_with_approval' als sicheres Alias.
    """
    api.register_tool(
        name="restart_with_approval",
        description=(
            "Startet AION neu — aber NUR nach expliziter Genehmigung durch den Nutzer. "
            "Dieses Tool MUSS statt 'self_restart' verwendet werden. "
            "Es fragt den Nutzer zuerst um Erlaubnis und bricht ab, wenn dieser ablehnt."
        ),
        func=lambda **kwargs: request_restart_approval(),
        input_schema={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
