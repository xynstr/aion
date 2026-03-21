import importlib.util
from pathlib import Path

PLUGINS_DIR = Path(__file__).parent / "plugins"

# Sammelt FastAPI-Router die Plugins während load_plugins() anmelden.
# aion_web.py liest diese Liste nach load_plugins() und bindet sie ein.
_pending_routers: list = []   # Liste von (router, prefix, tags)


class PluginAPI:
    def __init__(self, tool_registry):
        self.tool_registry = tool_registry

    def register_tool(self, name, description, func, input_schema=None):
        self.tool_registry[name] = {
            "description": description,
            "func": func,
            "input_schema": input_schema or {"type": "object", "properties": {}},
        }

    def register_router(self, router, prefix: str = "", tags: list = None):
        """Registriert einen FastAPI-APIRouter für Plugin-eigene Web-Endpunkte.

        Beispiel im Plugin:
            from fastapi import APIRouter
            router = APIRouter()

            @router.get("/api/meinplugin/status")
            async def status():
                return {"ok": True}

            def register(api):
                api.register_tool(...)
                api.register_router(router, prefix="", tags=["meinplugin"])
        """
        _pending_routers.append((router, prefix, tags or []))


def _read_readme_summary(plugin_dir: Path) -> str:
    """Liest den ersten beschreibenden Satz aus einer README.md.
    Überspringt Überschriften (#) und leere Zeilen — gibt erste inhaltliche Zeile zurück."""
    readme = plugin_dir / "README.md"
    if not readme.is_file():
        return ""
    try:
        for line in readme.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
    except Exception:
        pass
    return ""


def _load_file(file: Path, tool_registry: dict):
    """Lädt eine einzelne Plugin-Datei, ruft register(api) auf und liest README-Zusammenfassung."""
    spec = importlib.util.spec_from_file_location(f"plugin_{file.stem}", file)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        if hasattr(mod, "register"):
            api = PluginAPI(tool_registry)
            mod.register(api)
        # README-Erstzeile speichern — wird in System-Prompt als Plugin-Übersicht genutzt
        summary = _read_readme_summary(file.parent)
        if summary:
            tool_registry[f"__plugin_readme_{file.stem}"] = summary
    except Exception as exc:
        print(f"Fehler beim Laden von Modul {file.name}: {exc}")


def load_plugins(tool_registry: dict):
    global _pending_routers
    _pending_routers = []   # bei jedem Laden neu aufbauen

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
