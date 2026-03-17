import os
import json

def get_own_pid():
    """Gibt die eigene Prozess-ID (PID) zur cck."""
    return json.dumps({"ok": True, "pid": os.getpid()})

def register(api):
    api.register_tool(
        name="get_own_pid",
        description="Gibt die eigene Prozess-ID (PID) zur cck.",
        func=get_own_pid,
        input_schema={
            "type": "object",
            "properties": {}
        }
    )