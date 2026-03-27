"""
Todo-Tools — liest/schreibt todo.md im AION-Root.
Format: - [ ] Offene Aufgabe  |  - [x] Erledigte Aufgabe
"""
import threading
from pathlib import Path

TODO_FILE = Path(__file__).parent.parent.parent / "todo.md"
_TODO_LOCK = threading.Lock()


def _read_lines() -> list:
    if not TODO_FILE.exists():
        return []
    return TODO_FILE.read_text(encoding="utf-8").splitlines()


def _write_lines(lines: list):
    TODO_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_todos(lines: list) -> list:
    todos = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("- [ ] "):
            todos.append({"task": s[6:], "done": False, "_line": i})
        elif s.startswith("- [x] "):
            todos.append({"task": s[6:], "done": True, "_line": i})
    return todos


def register(api):

    def todo_add(task: str = "", **_) -> dict:
        if not task.strip():
            return {"ok": False, "error": "Kein Task-Text angegeben"}
        with _TODO_LOCK:
            lines = _read_lines()
            if not lines:
                lines = ["# AION TODO", ""]
            lines.append(f"- [ ] {task.strip()}")
            _write_lines(lines)
        return {"ok": True, "task": task.strip(), "file": str(TODO_FILE)}

    def todo_list(**_) -> dict:
        lines = _read_lines()
        todos = _parse_todos(lines)
        return {
            "open":  [t["task"] for t in todos if not t["done"]],
            "done":  [t["task"] for t in todos if t["done"]],
            "total": len(todos),
            "file":  str(TODO_FILE),
        }

    def todo_done(task: str = "", **_) -> dict:
        """Aufgabe als erledigt markieren."""
        task_clean = task.strip()
        with _TODO_LOCK:
            lines = _read_lines()
            for i, line in enumerate(lines):
                if line.strip() == f"- [ ] {task_clean}":
                    lines[i] = line.replace("- [ ] ", "- [x] ", 1)
                    _write_lines(lines)
                    return {"ok": True, "done": task_clean}
        return {"ok": False, "error": f"Offene Aufgabe nicht gefunden: {task_clean}"}

    def todo_remove(task: str = "", **_) -> dict:
        with _TODO_LOCK:
            lines = _read_lines()
            new = [l for l in lines
                   if l.strip() not in (f"- [ ] {task.strip()}", f"- [x] {task.strip()}")
                   and f"- [ ] {task}" not in l and f"- [x] {task}" not in l]
            if len(new) == len(lines):
                return {"ok": False, "error": f"Task nicht gefunden: {task}"}
            _write_lines(new)
        return {"ok": True, "removed": task}

    api.register_tool(
        name="todo_add",
        description="Neue Aufgabe zur todo.md im AION-Root hinzufügen. Schreibt '- [ ] task' in die File.",
        func=todo_add,
        input_schema={
            "type": "object",
            "properties": {"task": {"type": "string", "description": "Text der Aufgabe"}},
            "required": ["task"],
        },
    )
    api.register_tool(
        name="todo_list",
        description="Alle Aufgaben aus todo.md anzeigen — getrennt nach offen und erledigt.",
        func=todo_list,
        input_schema={"type": "object", "properties": {}},
    )
    api.register_tool(
        name="todo_done",
        description="Aufgabe in todo.md als erledigt markieren ([ ] → [x]).",
        func=todo_done,
        input_schema={
            "type": "object",
            "properties": {"task": {"type": "string", "description": "Exakter Task-Text (ohne '- [ ] ')"}},
            "required": ["task"],
        },
    )
    api.register_tool(
        name="todo_remove",
        description="Aufgabe komplett aus todo.md entfernen (egal ob offen oder erledigt).",
        func=todo_remove,
        input_schema={
            "type": "object",
            "properties": {"task": {"type": "string", "description": "Exakter Task-Text"}},
            "required": ["task"],
        },
    )
