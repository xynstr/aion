def register(api):
    import os
    import json
    todo_path = os.path.join(os.path.dirname(__file__), 'todo_list.json')

    def load_todos():
        if not os.path.exists(todo_path):
            return []
        with open(todo_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_todos(todos):
        with open(todo_path, 'w', encoding='utf-8') as f:
            json.dump(todos, f, ensure_ascii=False, indent=2)

    def add_todo(task: str = "", created: str = None, **_):
        todos = load_todos()
        todos.append({"task": task, "created": created})
        save_todos(todos)
        return {"ok": True, "task": task}

    def list_todos(**_):
        todos = load_todos()
        return {"todos": todos}

    def remove_todo(task: str = "", **_):
        todos = load_todos()
        todos = [t for t in todos if t["task"] != task]
        save_todos(todos)
        return {"ok": True, "removed": task}

    api.register_tool(
        name="todo_add",
        description="Fcgt eine neue Aufgabe zur To-Do-Liste hinzu.",
        func=add_todo,
        input_schema={"type": "object", "properties": {"task": {"type": "string"}, "created": {"type": "string"}}}
    )
    api.register_tool(
        name="todo_list",
        description="Listet alle aktuellen Aufgaben der To-Do-Liste auf.",
        func=list_todos,
        input_schema={"type": "object", "properties": {}}
    )
    api.register_tool(
        name="todo_remove",
        description="Entfernt eine Aufgabe aus der To-Do-Liste.",
        func=remove_todo,
        input_schema={"type": "object", "properties": {"task": {"type": "string"}}}
    )