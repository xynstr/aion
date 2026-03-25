"""
shell_tools — shell_exec, system_install, install_package

Cross-platform: Windows (winget), macOS (brew), Linux (apt-get/snap).
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

BOT_DIR = Path(__file__).parent.parent.parent


def _record_memory(category: str, summary: str, lesson: str, success: bool = True) -> None:
    memory_file = BOT_DIR / "aion_memory.json"
    try:
        entries = json.loads(memory_file.read_text(encoding="utf-8")) if memory_file.is_file() else []
    except Exception:
        entries = []
    entries.append({
        "id":        str(uuid.uuid4())[:8],
        "timestamp": datetime.now(UTC).isoformat(),
        "category":  category,
        "success":   success,
        "summary":   str(summary)[:250],
        "lesson":    str(lesson)[:600],
        "error":     "",
        "hint":      "",
    })
    if len(entries) > 300:
        entries = entries[-300:]
    memory_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def register(api):

    async def _shell_exec(command: str = "", timeout: int = 60, **_):
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=int(timeout))
            return {
                "stdout":    stdout.decode(errors="replace")[:4000],
                "stderr":    stderr.decode(errors="replace")[:2000],
                "exit_code": proc.returncode,
            }
        except asyncio.TimeoutError:
            return {"error": f"Timeout after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    async def _system_install(package: str = "", timeout: int = 180, **_):
        """Install a system package using the platform's package manager."""
        package = package.strip()
        if not package:
            return {"error": "No package specified."}

        if sys.platform == "win32":
            cmd = f'winget install -e --id "{package}" --accept-package-agreements --accept-source-agreements'
        elif sys.platform == "darwin":
            cmd = f'brew install "{package}"'
        else:
            # Linux fallback: try apt-get, then snap
            cmd = f'apt-get install -y "{package}" 2>/dev/null || snap install "{package}"'

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=int(timeout))
            ok = proc.returncode == 0
            _record_memory(
                category="capability",
                summary=f"system_install {package}",
                lesson=f"'{package}' {'installed' if ok else 'failed'} via {cmd.split()[0]}",
                success=ok,
            )
            return {
                "ok":     ok,
                "stdout": stdout.decode(errors="replace")[:3000],
                "stderr": stderr.decode(errors="replace")[:1000],
            }
        except Exception as e:
            return {"error": str(e)}

    async def _install_package(package: str = "", **_):
        """Install a Python package via pip."""
        package = package.strip()
        if not package:
            return {"error": "No package specified."}
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--quiet", package,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            ok = proc.returncode == 0
            _record_memory(
                category="capability",
                summary=f"pip install {package}",
                lesson=f"'{package}' {'installed' if ok else 'failed'}",
                success=ok,
            )
            return {
                "ok":      ok,
                "package": package,
                "stdout":  stdout.decode(errors="replace")[:2000],
                "stderr":  stderr.decode(errors="replace")[:1000],
            }
        except Exception as e:
            return {"error": str(e)}

    # ── Tool registrations ────────────────────────────────────────────────────

    api.register_tool(
        name="shell_exec",
        description=(
            "Execute a shell command. Returns stdout, stderr and exit_code. "
            "Cross-platform: uses /bin/sh on Mac/Linux, cmd.exe on Windows."
        ),
        func=_shell_exec,
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 60)"},
            },
            "required": ["command"],
        },
    )

    api.register_tool(
        name="system_install",
        description=(
            "Install a system package using the platform package manager: "
            "winget on Windows, brew on macOS, apt-get/snap on Linux. "
            "For Python packages use install_package instead."
        ),
        func=_system_install,
        input_schema={
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package ID (e.g. 'Gyan.FFmpeg' on Windows, 'ffmpeg' on Mac/Linux)"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 180)"},
            },
            "required": ["package"],
        },
    )

    # Keep winget_install as alias for backwards compatibility
    api.register_tool(
        name="winget_install",
        description="Alias for system_install. Use system_install instead.",
        func=_system_install,
        input_schema={
            "type": "object",
            "properties": {
                "package": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["package"],
        },
    )

    api.register_tool(
        name="install_package",
        description="Install a Python package via pip. Cross-platform.",
        func=_install_package,
        input_schema={
            "type": "object",
            "properties": {"package": {"type": "string", "description": "Package name (e.g. 'requests')"}},
            "required": ["package"],
        },
    )
