import importlib.util
import shutil
from pathlib import Path
from datetime import datetime

PLUGINS_DIR = Path(__file__).parent / "plugins"
SNAPSHOTS_DIR = Path(__file__).parent / ".snapshots"

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


# ---------------------------------------------------------------------------
# Snapshot / Rollback
# ---------------------------------------------------------------------------

def create_snapshot(plugin_name: str) -> str | None:
    """Erstellt einen Snapshot des aktuellen Plugin-Codes vor einer Änderung.
    Gibt den Snapshot-Pfad zurück oder None wenn kein bestehendes Plugin gefunden."""
    plugin_path = PLUGINS_DIR / plugin_name / f"{plugin_name}.py"
    if not plugin_path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = SNAPSHOTS_DIR / plugin_name / timestamp
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plugin_path, snapshot_dir / f"{plugin_name}.py")

    _cleanup_old_snapshots(plugin_name, keep=5)
    return str(snapshot_dir)


def restore_snapshot(plugin_name: str, snapshot_path: str = None) -> bool:
    """Stellt ein Plugin aus dem letzten (oder einem bestimmten) Snapshot wieder her."""
    if snapshot_path:
        snapshot_file = Path(snapshot_path) / f"{plugin_name}.py"
    else:
        plugin_snapshots = SNAPSHOTS_DIR / plugin_name
        if not plugin_snapshots.exists():
            return False
        snapshots = sorted(plugin_snapshots.iterdir())
        if not snapshots:
            return False
        snapshot_file = snapshots[-1] / f"{plugin_name}.py"

    if not snapshot_file.exists():
        return False

    plugin_path = PLUGINS_DIR / plugin_name / f"{plugin_name}.py"
    shutil.copy2(snapshot_file, plugin_path)
    return True


def list_snapshots(plugin_name: str) -> list[str]:
    """Gibt alle verfügbaren Snapshot-Timestamps für ein Plugin zurück."""
    plugin_snapshots = SNAPSHOTS_DIR / plugin_name
    if not plugin_snapshots.exists():
        return []
    return sorted(d.name for d in plugin_snapshots.iterdir() if d.is_dir())


def _cleanup_old_snapshots(plugin_name: str, keep: int = 5):
    """Löscht alte Snapshots, behält nur die letzten `keep` Versionen."""
    plugin_snapshots = SNAPSHOTS_DIR / plugin_name
    if not plugin_snapshots.exists():
        return
    snapshots = sorted(plugin_snapshots.iterdir())
    for old in snapshots[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


def load_plugin_safe(plugin_name: str, plugin_code: str, tool_registry: dict) -> dict:
    """Schreibt Plugin-Code, lädt es und prüft ob es korrekt registriert wurde.
    Bei Fehler wird automatisch der letzte Snapshot wiederhergestellt.

    Returns dict mit: ok, plugin, tools, snapshot, error, rolled_back
    """
    plugin_dir = PLUGINS_DIR / plugin_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = plugin_dir / f"{plugin_name}.py"

    # 1. Snapshot des bestehenden Plugins (falls vorhanden)
    snapshot_path = create_snapshot(plugin_name)

    # 2. Neuen Code schreiben
    plugin_path.write_text(plugin_code, encoding="utf-8")

    # 3. Isoliert laden und Health-Check
    test_registry: dict = {}
    try:
        spec = importlib.util.spec_from_file_location(f"plugin_{plugin_name}_healthcheck", plugin_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "register"):
            api = PluginAPI(test_registry)
            mod.register(api)
    except Exception as exc:
        # 4. Health-Check fehlgeschlagen → Rollback
        rolled_back = False
        if snapshot_path:
            rolled_back = restore_snapshot(plugin_name, snapshot_path)
            if rolled_back:
                plugin_path.write_text(
                    (Path(snapshot_path) / f"{plugin_name}.py").read_text(encoding="utf-8"),
                    encoding="utf-8"
                )
        else:
            # Kein Snapshot → kaputte Datei entfernen
            plugin_path.unlink(missing_ok=True)

        return {
            "ok": False,
            "error": str(exc),
            "rolled_back": rolled_back,
            "snapshot": snapshot_path,
        }

    # 5. Kein Fehler → vollständig in echte Registry laden
    load_plugins(tool_registry)

    return {
        "ok": True,
        "plugin": plugin_name,
        "tools": [k for k in test_registry if not k.startswith("__")],
        "snapshot": snapshot_path,
        "rolled_back": False,
    }


# ---------------------------------------------------------------------------
# README helper
# ---------------------------------------------------------------------------

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
