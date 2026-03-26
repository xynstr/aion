# REST API Reference

Base URL: `http://localhost:7000`

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/status` | Server status, model, uptime |
| `POST` | `/api/chat` | Chat — SSE stream |
| `POST` | `/api/reset` | Reset conversation history |
| `POST` | `/api/model` | Switch active model |
| `GET` | `/api/providers` | All registered providers + active model |
| `GET` | `/api/plugins` | All plugins with tools + load status |
| `POST` | `/api/plugins/reload` | Hot-reload all plugins |
| `POST` | `/api/plugins/enable` | Enable a plugin `{"name": "..."}` |
| `POST` | `/api/plugins/disable` | Disable a plugin `{"name": "..."}` |
| `GET` | `/api/keys` | API keys (masked) grouped by provider |
| `POST` | `/api/keys` | Save key to `.env` + update process |
| `GET` | `/api/memory` | Memory entries (`?search=`, `?limit=`, `?offset=`) |
| `DELETE` | `/api/memory` | Clear all memory |
| `GET` | `/api/config` | Configuration + statistics |
| `POST` | `/api/config/settings` | Update settings |
| `GET` | `/api/prompt/{name}` | Read prompt file (`rules`, `character`, `self`) |
| `POST` | `/api/prompt/{name}` | Save prompt file |
| `GET` | `/api/audio/{filename}` | Stream generated audio |
| `GET` | `/api/telegram/config` | Telegram token + whitelist status |
| `POST` | `/api/telegram/config` | Save Telegram token + whitelist |
| `GET` | `/api/claude-cli/status` | Claude CLI install + auth status |
| `POST` | `/api/claude-cli/login` | Start Claude subscription login |
| `GET` | `/api/oauth/google/start` | Begin Google OAuth for Gemini |
| `POST` | `/api/alexa` | Amazon Alexa Skill endpoint |
| `GET` | `/api/update-status` | Update state (version, available) |
| `POST` | `/api/update-trigger` | Force update check |

## SSE Stream (`POST /api/chat`)

```json
{ "message": "your message here" }
```

Events emitted during a response:

| Event | Payload | Description |
|-------|---------|-------------|
| `token` | `{"text": "..."}` | Partial text chunk (live stream) |
| `thought` | `{"text": "..."}` | AION's inner reasoning |
| `tool_call` | `{"name": "...", "args": {...}}` | Tool being called |
| `tool_result` | `{"name": "...", "result": "...", "ok": true}` | Tool result |
| `approval` | `{"message": "..."}` | Awaiting user confirmation |
| `done` | `{"full_response": "...", "response_blocks": [...]}` | Completion |
| `error` | `{"message": "..."}` | Error |
