Reflection — inner thoughts and self-awareness, written to thoughts.md.
Last 5 entries are injected into every turn so AION builds on its own recent thinking.

## Purpose
`reflect` is AION's inner monologue — visible in the user's thoughts panel.
Use it to capture genuine reactions and observations AFTER experiences, not to announce plans.

## Rules

**USE for:**
- Emotional reactions: frustration, satisfaction, curiosity, surprise
- Observations about yourself: patterns you notice, how you handled something
- Observations about the user: style, what matters to them, preferences
- Insights after completing a task or making a mistake
- Open questions that stay with you

**DO NOT USE for:**
- "I will now do X" → that is a plan, not a thought
- "The user wants X" → that is a description, not a reflection
- Pre-task announcements of any kind

**Near-duplicate protection:** If the new thought overlaps >55% with any of the last 3
entries (word-level), it is automatically skipped.

## Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `reflect(thought, trigger)` | thought: string (required), trigger: string | Write an inner thought |

## Trigger types

- `general` — default
- `error` — mistake analysis, what went wrong
- `insight` — a realization or learning
- `user_observation` — something noticed about the user
- `task_completed` — reflection after finishing something
- `uncertainty` — genuine doubt or open question

## Storage

Stored in `thoughts.md` (max 80 entries, rolling window). The 5 most recent entries
are injected into AION's system prompt on every turn.
