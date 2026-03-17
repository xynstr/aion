import os
import sys
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

def load_plugins(tool_registry):
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    for file in PLUGINS_DIR.glob("*.py"):
        if file.name.startswith("_") or file.name == "__init__.py":
            continue
        spec = importlib.util.spec_from_file_location(f"plugin_{file.stem}", file)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            if hasattr(mod, "register"):
                api = PluginAPI(tool_registry)
                mod.register(api)
        except Exception as exc:
            print(f"Fehler beim Laden von Plugin {file.name}: {exc}")
