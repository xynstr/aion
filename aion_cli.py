#!/usr/bin/env python3
"""
AION CLI  —  aion --cli
Cross-platform (Windows + macOS + Linux). Requires: rich
"""
import asyncio
import os
import sys
from pathlib import Path

# UTF-8 on Windows
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.chdir(Path(__file__).parent)

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.text import Text
    from rich import box as rbox
except ImportError:
    print("rich not installed — run: pip install rich")
    if sys.platform == "win32":
        try:
            input("Press Enter to close...")
        except Exception:
            pass
    sys.exit(1)

console = Console(highlight=False)


# ── helpers ───────────────────────────────────────────────────────────────────

def _stat_panel(label: str, value: str, color: str = "white") -> Panel:
    return Panel(
        Text(str(value), style=color, justify="center"),
        title=f"[dim]{label}[/dim]",
        border_style="bright_black",
        padding=(0, 2),
        expand=True,
    )


def print_header(aion_module) -> None:
    model  = getattr(aion_module, "MODEL", "?")
    n_tool = len(getattr(aion_module, "_plugin_tools", {}))
    try:
        mem = getattr(aion_module, "memory", None)
        n_mem = len(mem._entries) if mem and hasattr(mem, "_entries") else 0
    except Exception:
        n_mem = 0
    try:
        tf = Path(__file__).parent / "todo.md"
        n_todo = sum(1 for l in tf.read_text(encoding="utf-8").splitlines()
                     if l.strip().startswith("- [ ]")) if tf.exists() else 0
    except Exception:
        n_todo = 0

    console.print()
    console.print(Panel(
        Text("AION", style="bold cyan", justify="center"),
        subtitle="[dim]Autonomous Intelligent Operations Node[/dim]",
        border_style="cyan",
        padding=(0, 4),
    ))
    console.print(Columns([
        _stat_panel("Model",  model,         "cyan"),
        _stat_panel("Tools",  n_tool,        "white"),
        _stat_panel("Memory", n_mem,         "white"),
        _stat_panel("Todos",  n_todo or "✓", "green" if not n_todo else "white"),
    ], equal=True, expand=True))
    console.print()
    console.print(
        "  [dim]/help[/dim]  [dim]/stats[/dim]  "
        "[dim]/clear[/dim]  [dim]/model[/dim]  "
        "[dim]exit[/dim]"
    )
    console.print()


# ── main loop ─────────────────────────────────────────────────────────────────

async def main() -> None:
    console.print()

    # ── load AION ─────────────────────────────────────────────────────────────
    with console.status("[cyan]Loading AION…[/cyan]", spinner="dots"):
        try:
            import aion as _aion
        except ImportError as e:
            console.print(f"[red]Import error:[/red] {e}")
            console.print("[dim]Run from the AION directory.[/dim]")
            return

    console.print("[green]✓[/green] [dim]AION ready[/dim]")

    print_header(_aion)

    session = _aion.AionSession(channel="cli")
    try:
        await session.load_history(num_entries=20)
    except Exception:
        pass

    # ── repl ──────────────────────────────────────────────────────────────────
    while True:
        console.print("[dim]" + "─" * console.width + "[/dim]")

        try:
            user_input = input("  You › ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]  Session ended.[/dim]")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("exit", "quit", "bye", "/exit"):
            console.print("[dim]  Session ended.[/dim]")
            break

        if cmd in ("/help", "help", "?"):
            console.print(Panel(
                "\n".join([
                    "[cyan]exit[/cyan] / [cyan]quit[/cyan]   End session",
                    "[cyan]/help[/cyan]           This help",
                    "[cyan]/clear[/cyan]          Clear terminal",
                    "[cyan]/model[/cyan]          Show active model",
                    "[cyan]/stats[/cyan]          Show statistics",
                    "[cyan]/config[/cyan]         Config: /config list, set, get, unset",
                    "[cyan]/snapshots[/cyan]      Plugin snapshots: /snapshots [<plugin>] [restore <plugin> [<timestamp>]]",
                ]),
                title="Commands", border_style="bright_black", padding=(0, 2),
            ))
            continue

        if cmd == "/clear":
            console.clear()
            print_header(_aion)
            continue

        if cmd == "/model":
            console.print(f"\n  [dim]Model:[/dim]  [cyan]{getattr(_aion, 'MODEL', '?')}[/cyan]\n")
            continue

        if cmd == "/stats":
            console.print()
            print_header(_aion)
            continue

        if cmd.startswith("/config"):
            _parts = user_input.split(None, 3)
            _sub   = _parts[1] if len(_parts) > 1 else "list"
            _key   = _parts[2] if len(_parts) > 2 else None
            _val   = _parts[3] if len(_parts) > 3 else None
            import json as _j
            _cfg_path = Path(__file__).parent / "config.json"
            def _lcfg():
                return _j.loads(_cfg_path.read_text(encoding="utf-8")) if _cfg_path.is_file() else {}
            def _scfg(c):
                _cfg_path.write_text(_j.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            if _sub == "list":
                _c = _lcfg()
                if _c:
                    _w = max(len(k) for k in _c) + 2
                    console.print()
                    for k, v in sorted(_c.items()):
                        console.print(f"  [dim]{k:<{_w}}[/dim] [cyan]{v}[/cyan]")
                    console.print()
                else:
                    console.print("[dim]  config.json is empty[/dim]")
            elif _sub == "get" and _key:
                _val2 = _lcfg().get(_key)
                if _val2 is None:
                    console.print(f"[dim]  '{_key}' not set[/dim]")
                else:
                    console.print(f"\n  [dim]{_key} =[/dim]  [cyan]{_val2}[/cyan]\n")
            elif _sub == "set" and _key and _val is not None:
                try:
                    _parsed = _j.loads(_val)
                except Exception:
                    _parsed = _val
                _c = _lcfg(); _c[_key] = _parsed; _scfg(_c)
                console.print(f"  [green]✓[/green]  [dim]{_key} = {_parsed!r}[/dim]")
            elif _sub == "unset" and _key:
                _c = _lcfg()
                if _key in _c:
                    del _c[_key]; _scfg(_c)
                    console.print(f"  [green]✓[/green]  [dim]'{_key}' removed[/dim]")
                else:
                    console.print(f"  [yellow]![/yellow]  [dim]'{_key}' not found[/dim]")
            else:
                console.print("[dim]  /config [list | get <key> | set <key> <value> | unset <key>][/dim]")
            continue

        if cmd.startswith("/snapshots"):
            from plugin_loader import SNAPSHOTS_DIR, list_snapshots, restore_snapshot, load_plugins
            _parts = user_input.split(None, 3)
            _sub   = _parts[1] if len(_parts) > 1 else None
            # /snapshots restore <plugin> [<timestamp>]
            if _sub == "restore":
                _plugin_name = _parts[2] if len(_parts) > 2 else None
                _ts          = _parts[3] if len(_parts) > 3 else None
                if not _plugin_name:
                    console.print("[yellow]  Usage: /snapshots restore <plugin> [<timestamp>][/yellow]")
                else:
                    _snap_path = str(SNAPSHOTS_DIR / _plugin_name / _ts) if _ts else None
                    _ok = restore_snapshot(_plugin_name, _snap_path)
                    if _ok:
                        load_plugins(_aion._plugin_tools)
                        console.print(f"  [green]✓[/green]  [dim]{_plugin_name} restored from {_ts or 'latest'}[/dim]")
                    else:
                        console.print(f"  [red]✗[/red]  [dim]No snapshot found for '{_plugin_name}'[/dim]")
            # /snapshots <plugin>  — list timestamps
            elif _sub and _sub != "restore":
                _snaps = list_snapshots(_sub)
                if _snaps:
                    console.print(f"\n  [dim]Snapshots for[/dim] [cyan]{_sub}[/cyan]:")
                    for _t in _snaps:
                        _sf = SNAPSHOTS_DIR / _sub / _t / f"{_sub}.py"
                        _sz = f"{_sf.stat().st_size/1024:.1f} KB" if _sf.exists() else "?"
                        console.print(f"    [dim]{_t}[/dim]  [dim italic]{_sz}[/dim italic]")
                    console.print()
                else:
                    console.print(f"  [dim]No snapshots for '{_sub}'[/dim]")
            # /snapshots — list all
            else:
                _all: dict[str, list] = {}
                if SNAPSHOTS_DIR.is_dir():
                    for _pd in sorted(SNAPSHOTS_DIR.iterdir()):
                        if _pd.is_dir():
                            _all[_pd.name] = list_snapshots(_pd.name)
                if _all:
                    console.print()
                    _w2 = max(len(k) for k in _all) + 2
                    for _pn, _ts_list in sorted(_all.items()):
                        _cnt = len(_ts_list)
                        _latest = _ts_list[-1] if _ts_list else "—"
                        console.print(f"  [cyan]{_pn:<{_w2}}[/cyan] [dim]{_cnt} snapshot(s)  latest: {_latest}[/dim]")
                    console.print()
                else:
                    console.print("  [dim]No snapshots yet.[/dim]")
            continue

        # ── stream response ───────────────────────────────────────────────────
        console.print()
        response_buffer = []
        tool_lines      = []
        in_response     = False

        with console.status("[dim]Thinking…[/dim]", spinner="dots") as status:
            try:
                async for event in session.stream(user_input):
                    etype = event.get("type")

                    if etype == "thought":
                        text    = (event.get("text") or "").replace("\n", " ").strip()
                        trigger = event.get("trigger", "")
                        trig    = f" [dim italic][{trigger}][/dim italic]" if trigger else ""
                        status.update(f"[magenta]💭  {text[:80]}[/magenta]{trig}")

                    elif etype == "tool_call":
                        name     = event.get("tool", "")
                        args     = event.get("args", {})
                        args_str = str(args)
                        if len(args_str) > 60:
                            args_str = args_str[:60] + "…"
                        tool_lines.append((name, args_str, None))
                        status.update(f"[yellow]⚙  {name}[/yellow]")

                    elif etype == "tool_result":
                        ok     = event.get("ok", True)
                        result = str(event.get("result", {}))
                        if len(result) > 80:
                            result = result[:80] + "…"
                        if tool_lines:
                            last = tool_lines[-1]
                            tool_lines[-1] = (last[0], last[1], (ok, result))

                    elif etype == "token":
                        token = event.get("content", "")
                        if token:
                            response_buffer.append(token)

                    elif etype in ("done", "error"):
                        break

            except KeyboardInterrupt:
                console.print("\n[dim]  (Interrupted)[/dim]")
                console.print()
                continue

            except Exception as e:
                console.print(f"\n[red]  ✗  {e}[/red]")
                console.print()
                continue

        # ── print tool calls ──────────────────────────────────────────────────
        for name, args_str, outcome in tool_lines:
            line = Text()
            line.append("  ⚙  ", style="yellow")
            line.append(name, style="bold yellow")
            line.append(f"({args_str})", style="dim")
            if outcome is not None:
                ok, res = outcome
                line.append("  →  ", style="dim")
                line.append(("✓" if ok else "✗"), style="green" if ok else "red")
                line.append(f"  {res}", style="dim")
            console.print(line)

        if tool_lines:
            console.print()

        # ── print response ────────────────────────────────────────────────────
        if response_buffer:
            full = "".join(response_buffer)
            console.print(Text("  AION › ", style="bold cyan"), end="")
            try:
                console.print(Markdown(full))
            except Exception:
                console.print(full)

        console.print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("[dim]\n  Session ended.[/dim]")
