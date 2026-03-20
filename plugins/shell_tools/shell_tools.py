"""
shell_tools — Shell, winget, pip (shell_exec, winget_install, install_package)

War früher hardcodiert in aion.py/_dispatch().
Als Plugin hot-reloadbar per self_reload_tools.
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime, UTC
from pathlib import Path

BOT_DIR = Path(__file__).parent.parent.parent


def _record_memory(category: str, summary: str, lesson: str, success: bool = True) -> None:
    """Standalone-Memory-Write: liest Datei, appendiert, speichert."""
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
            return {"error": f"Timeout nach {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    async def _winget_install(package: str = "", timeout: int = 180, **_):
        package = package.strip()
        if not package:
            return {"error": "Kein Paket angegeben."}
        cmd = (
            f'winget install -e --id "{package}" '
            f'--accept-package-agreements --accept-source-agreements'
        )
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
                summary=f"winget install {package}",
                lesson=f"'{package}' {'installiert' if ok else 'Fehler'}",
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
        package = package.strip()
        if not package:
            return {"error": "Kein Paket angegeben."}
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
                lesson=f"'{package}' {'installiert' if ok else 'Fehler bei Installation'}",
                success=ok,
            )
            return {
                "ok":     ok,
                "package": package,
                "stdout": stdout.decode(errors="replace")[:2000],
                "stderr": stderr.decode(errors="replace")[:1000],
            }
        except Exception as e:
            return {"error": str(e)}

    # ── Tool-Registrierungen ──────────────────────────────────────────────────

    api.register_tool(
        name="shell_exec",
        description=(
            "Führt einen Shell-Befehl auf dem Windows-System aus. "
            "Gibt stdout, stderr und exit_code zurück."
        ),
        func=_shell_exec,
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["command"],
        },
    )

    api.register_tool(
        name="winget_install",
        description="Installiert ein Windows-Programm via winget.",
        func=_winget_install,
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
        description="Installiert ein Python-Paket via pip.",
        func=_install_package,
        input_schema={
            "type": "object",
            "properties": {"package": {"type": "string"}},
            "required": ["package"],
        },
    )
