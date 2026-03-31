"""
aion_permissions — Permissions, Channel Allowlist und Thinking Level für AION.
Extrahiert aus aion.py.
"""
from aion_config import _load_config

# ── Permissions ───────────────────────────────────────────────────────────────

PERMISSION_DEFAULTS: dict = {
    "shell_exec":      "ask",
    "install_package": "ask",
    "file_write":      "allow",
    "file_delete":     "ask",
    "self_modify":     "ask",
    "create_plugin":   "ask",
    "restart":         "ask",
    "web_search":      "allow",
    "web_fetch":       "allow",
    "telegram_auto":   "allow",
    "memory_write":    "allow",
    "schedule":        "ask",
}

PERMISSION_LABELS: dict = {
    "shell_exec":      "Shell commands (shell_exec)",
    "install_package": "Install packages (pip)",
    "file_write":      "Write / modify files",
    "file_delete":     "Delete files",
    "self_modify":     "Modify own code",
    "create_plugin":   "Create plugins",
    "restart":         "Restart AION",
    "web_search":      "Web search",
    "web_fetch":       "Fetch URLs",
    "telegram_auto":   "Send Telegram messages autonomously",
    "memory_write":    "Write to memory",
    "schedule":        "Create / modify scheduled tasks",
}

def _load_permissions() -> dict:
    perms = _load_config().get("permissions", {})
    return {k: perms.get(k, v) for k, v in PERMISSION_DEFAULTS.items()}

def _permissions_prompt(perms: dict) -> str:
    lines = ["=== PERMISSIONS ===",
             "These are your current permissions. Follow them strictly."]
    ask_list  = [PERMISSION_LABELS[k] for k, v in perms.items() if v == "ask"]
    deny_list = [PERMISSION_LABELS[k] for k, v in perms.items() if v == "deny"]
    if ask_list:
        lines.append("ASK first (get explicit user confirmation before doing these):")
        for l in ask_list:
            lines.append(f"  - {l}")
    if deny_list:
        lines.append("DENIED (refuse and explain if asked):")
        for l in deny_list:
            lines.append(f"  - {l}")
    lines.append("Everything not listed above: allowed freely.")
    return "\n".join(lines)


def _match_pattern(value: str, pattern: str) -> bool:
    """Prüft ob value auf pattern passt (unterstützt Wildcards wie 'telegram*')."""
    if pattern.endswith("*"):
        return value.startswith(pattern[:-1])
    return value == pattern


# ── Channel Allowlist (Security) ────────────────────────────────────────────────

def _check_channel_allowlist(channel: str) -> tuple[bool, str]:
    """Checks if a channel is allowed on the allowlist.

    Returns: (is_allowed, message)
    - Wenn channel_allowlist nicht gesetzt: alle Channels erlaubt
    - Wenn gesetzt: nur Channels in der Liste erlaubt
    - Wildcards: "telegram*", "discord*", "web*" possible
    """
    cfg = _load_config()
    allowlist = cfg.get("channel_allowlist", [])

    # Wenn leer oder nicht gesetzt: alles erlaubt
    if not allowlist:
        return True, ""

    # Check exact match or wildcard match
    for pattern in allowlist:
        if isinstance(pattern, str) and _match_pattern(channel, pattern):
            return True, ""

    return False, f"Channel '{channel}' ist nicht auf der Allowlist. Erlaubte Channels: {', '.join(allowlist)}"


# ── Thinking Level Control ─────────────────────────────────────────────────────

def _get_thinking_prompt(channel: str = "") -> str:
    """Returns additional system prompts based on Thinking Level.

    Thinking Levels:
    - "minimal": No additional reflection prompts
    - "standard" (default): Normal reflection for tool calls and complex problems
    - "deep": Ausgiebiges Nachdenken vor kritischen Entscheidungen
    - "ultra": Maximale Reflexion, jeder Schritt wird durchdacht

    config.json:
        "thinking_level": "standard"  (global)
        "thinking_overrides": {"telegram*": "deep", "default": "standard"}  (Channel-spezifisch)
    """
    cfg = _load_config()

    # Channel-spezifisches Override oder globales Level
    overrides = cfg.get("thinking_overrides", {})
    level = cfg.get("thinking_level", "standard")

    # Wildcard matching for channel overrides
    if channel:
        for pattern, override_level in overrides.items():
            if pattern == "default":
                continue
            if _match_pattern(channel, pattern):
                level = override_level
                break

    # Prompts for each level
    prompts = {
        "minimal": "",
        "standard": (
            "\n\n=== THINKING HINTS ===\n"
            "Before calling tools, briefly consider if your approach makes sense. "
            "If it's a complex decision, use the reflect() tool to think out loud."
        ),
        "deep": (
            "\n\n=== DEEP THINKING MODE ===\n"
            "For every significant decision:\n"
            "1. Use reflect() to consider multiple approaches\n"
            "2. Evaluate risks and benefits\n"
            "3. Think about edge cases\n"
            "4. Only then call the tool\n"
            "Be thorough. The user values careful thinking over speed."
        ),
        "ultra": (
            "\n\n=== ULTRA THINKING MODE ===\n"
            "Extensive thinking before EVERY tool call:\n"
            "- Use reflect() multiple times if needed\n"
            "- Break down complex problems into steps\n"
            "- Consider what could go wrong\n"
            "- Verify assumptions\n"
            "- Think about the user's real intent vs. literal request\n"
            "This is not a chat. This is collaborative problem-solving with deep analysis."
        ),
    }
    return prompts.get(level, prompts["standard"])
