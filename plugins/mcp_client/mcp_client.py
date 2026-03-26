"""
AION Plugin: MCP Client
=======================
Connects AION to any MCP (Model Context Protocol) server.
Each server's tools are automatically registered as AION tools (mcp_{server}_{tool}).

Config: mcp_servers.json in the project root (committable — no secrets)
Secrets: stored in the credentials vault (key: mcp_{server_name})

mcp_servers.json format:
{
  "servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "vault_env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "mcp_github"}
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/Paul/Desktop"]
    }
  }
}

vault_env: maps environment variable names to vault credential keys.
           The plugin reads the value from the vault and injects it as env for the subprocess.

Tools registered per server:
  mcp_{server_name}_{tool_name}  — callable like any other AION tool
  mcp_list_servers               — lists all configured servers and their tools
"""

import asyncio
import json
import os
import re
from contextlib import AsyncExitStack
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).parent.parent.parent
CONFIG_FILE = ROOT_DIR / "mcp_servers.json"
VAULT_DIR   = ROOT_DIR / "credentials"
KEY_FILE    = VAULT_DIR / ".vault.key"

# ── Session registry (lazy connections) ───────────────────────────────────────
_sessions:    dict = {}   # server_name → ClientSession
_exit_stacks: dict = {}   # server_name → AsyncExitStack
_server_tools: dict = {}  # server_name → {tool_name: tool_obj}


# ── Vault helper ───────────────────────────────────────────────────────────────

def _vault_read(key: str) -> str | None:
    """Reads a value from the credentials vault. Returns None if not found."""
    try:
        from cryptography.fernet import Fernet
        if not KEY_FILE.exists():
            return None
        fernet = Fernet(KEY_FILE.read_bytes().strip())
        name = re.sub(r"[^\w\-]", "_", key.lower().strip())
        name = re.sub(r"_+", "_", name).strip("_")
        path = VAULT_DIR / f"{name}.md.enc"
        if not path.exists():
            return None
        return fernet.decrypt(path.read_bytes()).decode("utf-8").strip()
    except Exception:
        return None


# ── Connection management ──────────────────────────────────────────────────────

async def _ensure_connected(server_name: str, config: dict):
    """Lazily connect to an MCP server. Reuses existing session if available."""
    if server_name in _sessions:
        return _sessions[server_name]

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        raise RuntimeError(
            "Package 'mcp' not installed. Run: pip install mcp"
        )

    # Build env: start from current env, inject vault secrets
    env = os.environ.copy()
    for env_key, vault_key in config.get("vault_env", {}).items():
        val = _vault_read(vault_key)
        if val:
            # Vault may store full markdown text — extract first non-empty line
            first_line = next((l.strip() for l in val.splitlines() if l.strip()), val)
            env[env_key] = first_line

    params = StdioServerParameters(
        command=config["command"],
        args=config.get("args", []),
        env=env,
    )

    exit_stack = AsyncExitStack()
    try:
        read, write = await exit_stack.enter_async_context(stdio_client(params))
        session = await exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        # Discover tools
        tools_response = await session.list_tools()
        _server_tools[server_name] = {t.name: t for t in tools_response.tools}

        _sessions[server_name]    = session
        _exit_stacks[server_name] = exit_stack
        print(f"[mcp_client] {server_name}: {len(_server_tools[server_name])} tools loaded")
        return session
    except Exception as e:
        await exit_stack.aclose()
        raise RuntimeError(f"Failed to connect to MCP server '{server_name}': {e}") from e


async def _disconnect(server_name: str):
    """Disconnect from an MCP server and clean up."""
    if server_name in _exit_stacks:
        try:
            await _exit_stacks[server_name].aclose()
        except Exception:
            pass
        _sessions.pop(server_name, None)
        _exit_stacks.pop(server_name, None)
        _server_tools.pop(server_name, None)


# ── Tool factory ───────────────────────────────────────────────────────────────

def _make_tool_fn(server_name: str, tool_name: str, config: dict):
    """Returns an async function that calls a specific MCP tool."""
    async def _call(**kwargs):
        # Reconnect if session dropped
        if server_name not in _sessions:
            try:
                await _ensure_connected(server_name, config)
            except Exception as e:
                return json.dumps({"error": str(e)})

        session = _sessions[server_name]
        try:
            result = await session.call_tool(tool_name, arguments=kwargs)
            # Extract text content from result
            parts = []
            for c in (result.content or []):
                if hasattr(c, "text"):
                    parts.append(c.text)
                elif hasattr(c, "data"):
                    parts.append(f"[image: {getattr(c, 'mimeType', 'unknown')}]")
                else:
                    parts.append(str(c))
            return "\n".join(parts) if parts else json.dumps({"ok": True})
        except Exception as e:
            # Session may have died — clear it so next call reconnects
            _sessions.pop(server_name, None)
            return json.dumps({"error": f"MCP call failed: {e}"})

    _call.__name__ = f"mcp_{server_name}_{tool_name}"
    return _call


def _build_input_schema(tool_obj) -> dict:
    """Convert MCP tool input schema to AION tool schema format."""
    try:
        schema = tool_obj.inputSchema
        if isinstance(schema, dict):
            return schema
    except Exception:
        pass
    return {"type": "object", "properties": {}}


# ── Management tools ───────────────────────────────────────────────────────────

async def _mcp_list_servers(**_) -> str:
    """Lists all configured MCP servers and their loaded tools."""
    if not CONFIG_FILE.exists():
        return json.dumps({"error": "mcp_servers.json not found"})
    try:
        servers = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("servers", {})
    except Exception as e:
        return json.dumps({"error": str(e)})

    result = {}
    for name in servers:
        if name in _server_tools:
            result[name] = {"status": "connected", "tools": list(_server_tools[name].keys())}
        else:
            result[name] = {"status": "not connected"}
    return json.dumps(result, ensure_ascii=False, indent=2)


async def _mcp_connect_server(server: str = "", **_) -> str:
    """Manually connect to a configured MCP server by name."""
    if not CONFIG_FILE.exists():
        return json.dumps({"error": "mcp_servers.json not found"})
    try:
        servers = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("servers", {})
    except Exception as e:
        return json.dumps({"error": str(e)})
    if server not in servers:
        return json.dumps({"error": f"Server '{server}' not in mcp_servers.json"})
    try:
        await _ensure_connected(server, servers[server])
        return json.dumps({"ok": True, "tools": list(_server_tools.get(server, {}).keys())})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Plugin registration ────────────────────────────────────────────────────────

def register(api):
    """Register all MCP server tools as AION tools."""
    if not CONFIG_FILE.exists():
        # No config yet — register only management tools
        api.register_tool(
            "mcp_list_servers",
            "List all configured MCP servers and their tools. "
            "Config file: mcp_servers.json in project root.",
            _mcp_list_servers,
        )
        return

    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        servers = config.get("servers", {})
    except Exception as e:
        print(f"[mcp_client] Error reading mcp_servers.json: {e}")
        return

    # Management tools
    api.register_tool(
        "mcp_list_servers",
        "List all configured MCP servers and their connection status.",
        _mcp_list_servers,
    )
    api.register_tool(
        "mcp_connect_server",
        "Connect to a configured MCP server by name.",
        _mcp_connect_server,
        {"type": "object", "properties": {"server": {"type": "string", "description": "Server name from mcp_servers.json"}}, "required": ["server"]},
    )

    # Eagerly connect and register all server tools at startup
    for server_name, server_config in servers.items():
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule connection as background task
                asyncio.ensure_future(_register_server_async(api, server_name, server_config))
            else:
                loop.run_until_complete(_register_server_async(api, server_name, server_config))
        except Exception as e:
            print(f"[mcp_client] Could not schedule connection for '{server_name}': {e}")


async def _register_server_async(api, server_name: str, server_config: dict):
    """Connect to server and register its tools in the AION tool registry."""
    try:
        await _ensure_connected(server_name, server_config)
        for tool_name, tool_obj in _server_tools.get(server_name, {}).items():
            aion_tool_name = f"mcp_{server_name}_{tool_name}"
            desc = getattr(tool_obj, "description", "") or f"MCP tool: {tool_name} (server: {server_name})"
            api.register_tool(
                aion_tool_name,
                f"[MCP:{server_name}] {desc}",
                _make_tool_fn(server_name, tool_name, server_config),
                _build_input_schema(tool_obj),
            )
    except Exception as e:
        print(f"[mcp_client] {server_name}: {e}")
