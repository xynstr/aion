# mcp_client

Connects AION to any MCP (Model Context Protocol) server. Each server's tools are automatically available as AION tools.

MCP is an open standard by Anthropic — over 1,700 ready-made servers exist for GitHub, Notion, Postgres, Stripe, Home Assistant, Spotify, and more.

## Setup

1. Install the MCP package:
   ```
   pip install mcp
   ```

2. Create `mcp_servers.json` in the project root:
   ```json
   {
     "servers": {
       "github": {
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-github"],
         "vault_env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "mcp_github"}
       }
     }
   }
   ```

3. Store secrets in the vault:
   ```
   credential_write("mcp_github", "ghp_your_token_here")
   ```

4. Restart AION — tools appear automatically as `mcp_{server}_{tool}`

## Config format

| Field | Description |
|---|---|
| `command` | Executable to start the server (`npx`, `python`, `uvx`) |
| `args` | Arguments passed to the command |
| `vault_env` | Map of `ENV_VAR → vault_key` for secrets |

## Tools registered

- `mcp_list_servers` — show all configured servers and connection status
- `mcp_connect_server` — manually connect to a server by name
- `mcp_{server}_{tool}` — one tool per server tool, auto-registered at startup

## Example servers

```json
{
  "servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/Paul/Documents"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "vault_env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "mcp_github"}
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "vault_env": {"POSTGRES_URL": "mcp_postgres"}
    }
  }
}
```
