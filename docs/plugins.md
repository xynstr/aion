# Plugin Development

Every plugin lives in `plugins/<name>/<name>.py` and exports a `register(api)` function.

## Minimal Example

```python
# plugins/my_plugin/my_plugin.py

def register(api):
    def my_tool(param: str = "", **_) -> dict:
        return {"ok": True, "result": f"processed: {param}"}

    api.register_tool(
        name="my_tool",
        description="Short description shown to the LLM",
        func=my_tool,
        input_schema={
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "Input parameter"}
            },
            "required": ["param"]
        }
    )
```

> **Always use keyword args:** `def fn(param: str = "", **_)` — never `def fn(input: dict)`.

## Adding HTTP Routes

```python
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/myplugin/status")
async def status():
    return {"ok": True}

def register(api):
    api.register_tool(...)
    api.register_router(router, tags=["myplugin"])
```

## Tool Tiers

```python
api.register_tool(name="my_tool", ..., tier=2)
# tier=1 (default): always in LLM schemas
# tier=2: contextual — excluded by default, included when relevant
```

## Retry Policy

```python
api.register_tool(
    name="my_tool",
    ...,
    retry_policy={"max": 3, "backoff": 2.0, "on": ["network", "timeout"]}
)
```

## Hot-Reload

```
POST /api/plugins/reload
```
or **Plugins → ↺ Reload** in the Web UI.

## Available Plugins

| Plugin | Tools | Description |
|--------|-------|-------------|
| `core_tools` | continue_work, read_self_doc, system_info, memory_record | Core agent tools |
| `shell_tools` | shell_exec, winget_install, install_package | Shell + package management |
| `web_tools` | web_search, web_fetch | Search + HTTP |
| `file_tools` | file_read, file_write, file_replace_lines | File operations |
| `scheduler` | schedule_add, schedule_list, schedule_remove, schedule_toggle | Cron + interval scheduler |
| `telegram_bot` | send_telegram_message | Telegram: text + images + voice |
| `discord_bot` | send_discord_message | Discord: DMs + @mentions |
| `slack_bot` | send_slack_message | Slack: Socket Mode |
| `alexa_plugin` | — | Amazon Alexa Skill endpoint |
| `playwright_browser` | browser_open, browser_screenshot, browser_click, … | Browser automation (8 tools) |
| `desktop` | desktop_screenshot, desktop_click, desktop_type, … | Desktop automation via pyautogui |
| `multi_agent` | delegate_to_agent, sessions_list, sessions_send, sessions_history | Sub-agent delegation |
| `claude_cli_provider` | ask_claude, claude_cli_login, claude_cli_status | Claude subscription |
| `gemini_provider` | — | Google Gemini provider |
| `anthropic_provider` | — | Anthropic Claude (API key) |
| `deepseek_provider` | — | DeepSeek provider |
| `grok_provider` | — | xAI Grok provider |
| `ollama_provider` | — | Local Ollama provider |
| `audio_pipeline` | audio_tts, audio_transcribe | TTS + STT |
| `mcp_client` | mcp_* (dynamic) | MCP server integrations |
| `credentials` | credential_write, credential_read, credential_list, credential_delete | Encrypted vault |
| `character_manager` | — | Personality evolution |
| `mood_engine` | mood_check, mood_set | 5-state mood system |
| `proactive` | — | Morning task briefings |
| `heartbeat` | — | Keep-alive + autonomous todo processing |
| `updater` | check_for_updates | GitHub release checks |
| `web_tunnel` | tunnel_start, tunnel_stop, tunnel_status | HTTPS external access |
| `smart_patch` | self_patch_code, file_replace_lines | Code patching |
| `image_search` | image_search | Image search (Openverse + Bing) |
| `docx_tool` | create_docx | Create Word documents |
| `todo_tools` | todo_add, todo_list, todo_done | Task management |
