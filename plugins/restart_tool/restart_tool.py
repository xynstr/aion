import os
import sys
import subprocess
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

    try:
        # Starte einen neuen AION-Prozess
        subprocess.Popen([sys.executable, str(aion_py_path)], creationflags=subprocess.CREATE_NEW_CONSOLE)
        
        # Beende den aktuellen Prozess
        print("AION wird neu gestartet... aktueller Prozess wird beendet.")
        sys.exit(0)
        
    except Exception as e:
        return {'ok': False, 'error': f'Fehler beim Neustart: {e}'}

def register(api):
    """Registriert das self_restart Tool."""
    api.register_tool(
        name="self_restart",
        description="Startet AION neu: loescht Caches, startet neuen Prozess, beendet aktuellen.",
        func=self_restart_func,
        input_schema={"type": "object", "properties": {}}
    )