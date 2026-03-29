Focus Manager — persistent task focus injected into every turn.
Prevents topic drift on multi-step tasks by reminding AION of the current goal.

## How it works
The active focus is stored in `focus_state.json` and injected into the effective
system prompt on every turn. AION receives a clear reminder: "You are currently
working on: [task]. Do not get distracted."

## Tools

| Tool | Description |
|------|-------------|
| `focus_set(task)` | Set the current task focus (replaces any previous focus) |
| `focus_get()` | Read the currently active focus |
| `focus_clear()` | Clear the focus when the task is done |

## When to use

- Starting a multi-step task: `focus_set("Refactor plugin_loader.py — split into load/register")`
- User sends unrelated message mid-task: AION acknowledges but stays on focus
- Task fully completed: `focus_clear()` — required, otherwise old focus persists

## Notes
- Only one focus at a time. `focus_set` overwrites the previous one.
- Focus persists across restarts (stored in file, not memory).
- Keep focus descriptions short and action-oriented (< 100 chars).
