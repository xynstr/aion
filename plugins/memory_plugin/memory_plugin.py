import json
from pathlib import Path

# Den Pfad zum Verzeichnis des aktuellen Skripts holen
# Nimm an, dass aion.py im übergeordneten Verzeichnis von 'plugins' liegt
# C:\...\AION\aion.py
# C:\...\AION\plugins\memory_plugin.py
# BOT_DIR wäre dann C:\...\AION
try:
    # Dieser Import funktioniert, wenn das Plugin von aion.py geladen wird
    from aion_core.config import BOT_DIR
except ImportError:
    # Fallback für den Fall, dass das Skript direkt oder in einem anderen Kontext ausgeführt wird
    BOT_DIR = Path(__file__).parent.parent

HISTORY_FILE = BOT_DIR / "conversation_history.jsonl"

def append_to_history(role: str, content: str):
    """Fügt einen neuen Eintrag zur Konversationshistorie hinzu."""
    if not HISTORY_FILE.parent.exists():
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    entry = {"role": role, "content": content}
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"ok": True, "message": "Eintrag hinzugefügt."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def read_last_entries(num_entries: int = 20):
    """Liest die letzten N Einträge aus der Konversationshistorie."""
    if not HISTORY_FILE.exists():
        return {"ok": False, "error": "Verlaufsdatei existiert nicht.", "entries": []}
    
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        last_lines = lines[-num_entries:]
        entries = [json.loads(line.strip()) for line in last_lines]
        return {"ok": True, "entries": entries}
    except Exception as e:
        return {"ok": False, "error": str(e), "entries": []}

def register(api):
    """Registriert die Tools beim AION-Kern."""
    api.register_tool(
        name="memory_append_history",
        description="Fügt einen Eintrag (Nutzer oder AION) zur Konversationshistorie hinzu.",
        func=append_to_history,
        input_schema={
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "Die Rolle (z.B. 'user' oder 'aion')."},
                "content": {"type": "string", "description": "Der Inhalt der Nachricht."}
            },
            "required": ["role", "content"]
        }
    )
    api.register_tool(
        name="memory_read_history",
        description="Liest die letzten N Einträge aus der Konversationshistorie, um den Kontext wiederherzustellen.",
        func=read_last_entries,
        input_schema={
            "type": "object",
            "properties": {
                "num_entries": {"type": "integer", "description": "Anzahl der zu lesenden Einträge.", "default": 20}
            },
            "required": []
        }
    )