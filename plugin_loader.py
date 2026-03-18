import importlib.util
from pathlib import Path

PLUGINS_DIR = Path(__file__).parent / "plugins"


class PluginAPI:
    def __init__(self, tool_registry):
        self.tool_registry = tool_registry

    def register_tool(self, name, description, func, input_schema=None):
        self.tool_registry[name] = {
            "description": description,
            "func": func,
            "input_schema": input_schema or {"type": "object", "properties": {}},
        }


def _load_file(file: Path, tool_registry: dict):
    """Lädt eine einzelne Plugin-Datei und ruft register(api) auf."""
    spec = importlib.util.spec_from_file_location(f"plugin_{file.stem}", file)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        if hasattr(mod, "register"):
            api = PluginAPI(tool_registry)
            mod.register(api)
    except Exception as exc:
        print(f"Fehler beim Laden von Modul {file.name}: {exc}")


def load_plugins(tool_registry: dict):
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        return

    loaded = set()

    # Konvention 1: Unterordner — plugins/{name}/{name}.py
    # Ignoriert _backups/ und andere Unterordner die mit _ beginnen
    for subfolder in sorted(PLUGINS_DIR.iterdir()):
        if not subfolder.is_dir():
            continue
        if subfolder.name.startswith("_"):
            continue  # _backups/, __pycache__ etc. ignorieren
        plugin_file = subfolder / f"{subfolder.name}.py"
        if plugin_file.is_file():
            _load_file(plugin_file, tool_registry)
            loaded.add(plugin_file.stem)

    # Konvention 2: Flache .py-Dateien direkt in plugins/ (Rückwärtskompatibilität
    # und nutzer-erstellte Plugins die noch nicht in Unterordnern liegen)
    for file in sorted(PLUGINS_DIR.glob("*.py")):
        if file.name.startswith("_") or file.name == "__init__.py":
            continue
        if ".backup" in file.name:
            continue  # Backup-Dateien (von self_patch_code erstellt) ignorieren
        if file.stem in loaded:
            continue  # bereits über Unterordner geladen
        _load_file(file, tool_registry)
