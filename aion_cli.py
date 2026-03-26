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
    from rich.table import Table
except ImportError:
    print("rich not installed — run: pip install rich")
    if sys.platform == "win32":
        try:
            input("Press Enter to close...")
        except Exception:
            pass
    sys.exit(1)

console = Console(highlight=False)

# ── Onboarding Plugin Catalogue ───────────────────────────────────────────────
# (name, description, recommended_default)
_PLUGIN_GROUPS: list[tuple[str, str, list[tuple[str, str, bool]]]] = [
    ("Productivity", "⭐ Recommended", [
        ("character_manager", "Manages AION's personality + character evolution", True),
        ("mood_engine",       "Dynamic mood system — influences tone and style",  True),
        ("credentials",       "Encrypted local storage for API keys & passwords", True),
        ("proactive",         "Daily memory analysis to surface open tasks",      True),
    ]),
    ("Messaging", "", [
        ("telegram_bot",  "Bidirectional Telegram bot — text, images, voice", False),
        ("discord_bot",   "Discord bot integration",                          False),
        ("slack_bot",     "Slack bot integration",                            False),
    ]),
    ("AI Providers", "", [
        ("anthropic_provider", "Claude models via Anthropic API",  False),
        ("gemini_provider",    "Google Gemini models",             False),
        ("ollama_provider",    "Local LLMs via Ollama",            False),
        ("grok_provider",      "xAI Grok models",                  False),
        ("deepseek_provider",  "DeepSeek V3 / R1 models",         False),
    ]),
    ("Automation", "", [
        ("playwright_browser", "Full browser control via Playwright",    False),
        ("desktop",            "Desktop automation: screenshot, click",  False),
        ("mcp_client",         "Connect to any MCP server",              False),
        ("audio_pipeline",     "Audio I/O, TTS and STT pipeline",       False),
    ]),
    ("Extended", "", [
        ("multi_agent",  "Delegate tasks to isolated sub-agents", False),
        ("web_tunnel",   "Secure HTTPS access from outside LAN",  False),
        ("docx_tool",    "Create and edit Word documents",         False),
        ("image_search", "Search images by keyword",              False),
        ("moltbook",     "Moltbook platform integration",         False),
    ]),
]


def _run_setup() -> None:
    """Interactive first-time plugin selection wizard (runs before aion import)."""
    from plugin_loader import PLUGINS_DIR, DEFAULT_ENABLED, DISABLED_FILE, _save_disabled

    console.print()
    console.print(Panel(
        "[bold cyan]AION — First-Time Setup[/bold cyan]\n"
        "[dim]Select which plugins to activate. Core plugins are always enabled.[/dim]",
        border_style="cyan",
        padding=(1, 4),
    ))
    console.print()

    selected: set[str] = set()   # user-selected optional plugins

    for group_name, group_badge, plugins in _PLUGIN_GROUPS:
        badge_str = f" [yellow]{group_badge}[/yellow]" if group_badge else ""
        # Build table for this group
        t = Table(box=rbox.SIMPLE, show_header=False, padding=(0, 1), expand=False)
        t.add_column("check", width=4)
        t.add_column("name",  style="cyan", width=22)
        t.add_column("desc",  style="dim")

        defaults: list[str] = []
        for name, desc, recommended in plugins:
            mark  = "[green]✓[/green]" if recommended else "[ ]"
            badge = " [yellow dim]REC[/yellow dim]" if recommended else ""
            t.add_row(mark, name, desc + badge)
            if recommended:
                defaults.append(name)

        console.print(f"  [bold white]── {group_name}[/bold white]{badge_str}")
        console.print(t)

        # Ask group-level: enable recommended defaults? (y), enable all? (a), skip? (n)
        if defaults:
            ans = console.input(
                f"  Enable recommended ({', '.join(defaults)})? "
                "[dim][[green]y[/green]=recommended | [cyan]a[/cyan]=all | Enter=skip][/dim] "
            ).strip().lower()
        else:
            ans = console.input(
                f"  Enable any in '{group_name}'? "
                "[dim][[cyan]a[/cyan]=all | Enter=skip][/dim] "
            ).strip().lower()

        if ans == "a":
            selected.update(n for n, _, _ in plugins)
        elif ans in ("y", "yes") and defaults:
            selected.update(defaults)
        # else: skip group

        console.print()

    # Compute what to disable: everything not in DEFAULT_ENABLED and not selected
    all_plugins: set[str] = set()
    if PLUGINS_DIR.exists():
        all_plugins = {
            d.name for d in PLUGINS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith("_")
        }
    to_disable = all_plugins - DEFAULT_ENABLED - selected

    # Summary
    enabled_extra = sorted(selected)
    console.print("  [bold]Setup Summary[/bold]")
    console.print(f"  [dim]Core plugins (always on):[/dim] {len(DEFAULT_ENABLED)}")
    if enabled_extra:
        console.print(f"  [dim]Additional enabled:[/dim]     [green]{', '.join(enabled_extra)}[/green]")
    else:
        console.print("  [dim]Additional enabled:[/dim]     [dim](none — you can enable later via /plugins)[/dim]")
    console.print()

    try:
        input("  Press Enter to start AION…")
    except (EOFError, KeyboardInterrupt):
        pass

    _save_disabled(to_disable)
    console.print("  [green]✓[/green] [dim]Setup complete.[/dim]")
    console.print()


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


# ── command handlers ─────────────────────────────────────────────────────────

def _cmd_config(user_input: str, _aion=None) -> None:
    import config_store as _cs
    import json as _j
    _parts = user_input.split(None, 3)
    _sub   = _parts[1] if len(_parts) > 1 else "list"
    _key   = _parts[2] if len(_parts) > 2 else None
    _val   = _parts[3] if len(_parts) > 3 else None
    if _sub == "list":
        _c = _cs.load()
        if _c:
            _w = max(len(k) for k in _c) + 2
            console.print()
            for k, v in sorted(_c.items()):
                console.print(f"  [dim]{k:<{_w}}[/dim] [cyan]{v}[/cyan]")
            console.print()
        else:
            console.print("[dim]  config.json is empty[/dim]")
    elif _sub == "get" and _key:
        _val2 = _cs.load().get(_key)
        if _val2 is None:
            console.print(f"[dim]  '{_key}' not set[/dim]")
        else:
            console.print(f"\n  [dim]{_key} =[/dim]  [cyan]{_val2}[/cyan]\n")
    elif _sub == "set" and _key and _val is not None:
        try:
            _parsed = _j.loads(_val)
        except Exception:
            _parsed = _val
        _cs.update(_key, _parsed)
        console.print(f"  [green]✓[/green]  [dim]{_key} = {_parsed!r}[/dim]")
    elif _sub == "unset" and _key:
        _c = _cs.load()
        if _key in _c:
            del _c[_key]
            _cs.save(_c)
            console.print(f"  [green]✓[/green]  [dim]'{_key}' removed[/dim]")
        else:
            console.print(f"  [yellow]![/yellow]  [dim]'{_key}' not found[/dim]")
    else:
        console.print("[dim]  /config [list | get <key> | set <key> <value> | unset <key>][/dim]")


def _cmd_snapshots(user_input: str, _aion) -> None:
    from plugin_loader import SNAPSHOTS_DIR, list_snapshots, restore_snapshot, load_plugins
    _parts = user_input.split(None, 3)
    _sub   = _parts[1] if len(_parts) > 1 else None
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


def _cmd_plugins(user_input: str, _aion) -> None:
    from plugin_loader import get_disabled, enable_plugin, disable_plugin, load_plugins, PLUGINS_DIR
    _pparts = user_input.split(None, 2)
    _psub   = _pparts[1] if len(_pparts) > 1 else None
    _pname  = _pparts[2] if len(_pparts) > 2 else None
    if _psub == "enable" and _pname:
        enable_plugin(_pname)
        load_plugins(_aion._plugin_tools)
        if hasattr(_aion, "invalidate_sys_prompt_cache"):
            _aion.invalidate_sys_prompt_cache()
        console.print(f"  [green]✓[/green]  [dim]{_pname} enabled[/dim]")
    elif _psub == "disable" and _pname:
        disable_plugin(_pname)
        load_plugins(_aion._plugin_tools)
        if hasattr(_aion, "invalidate_sys_prompt_cache"):
            _aion.invalidate_sys_prompt_cache()
        console.print(f"  [green]✓[/green]  [dim]{_pname} disabled[/dim]")
    else:
        disabled = get_disabled()
        console.print()
        if PLUGINS_DIR.exists():
            _pw = 26
            for _pd in sorted(PLUGINS_DIR.iterdir()):
                if not _pd.is_dir() or _pd.name.startswith("_"):
                    continue
                _is_off = _pd.name in disabled
                _status = "[red]off[/red]" if _is_off else "[green]on [/green]"
                console.print(f"  {_status}  [{'dim' if _is_off else 'cyan'}]{_pd.name:<{_pw}}[/{'dim' if _is_off else 'cyan'}]")
        console.print()
        console.print("  [dim]/plugins enable <name>  |  /plugins disable <name>[/dim]")
        console.print()


def _cmd_telegram(user_input: str, _aion=None) -> None:
    import config_store as _tcs
    _tparts = user_input.split(None, 2)
    _tsub   = _tparts[1] if len(_tparts) > 1 else None
    _tval   = _tparts[2] if len(_tparts) > 2 else None
    if _tsub == "token" and _tval:
        _tcs.update("telegram_token", _tval)
        try:
            (Path.home() / ".aion_telegram_token").write_text(_tval)
        except Exception:
            pass
        console.print(f"  [green]✓[/green]  [dim]Token saved ({_tval[:12]}…)[/dim]")
    elif _tsub == "add" and _tval:
        _allowed = _tcs.load().get("telegram_allowed_ids", [])
        if str(_tval) not in [str(i) for i in _allowed]:
            _allowed.append(str(_tval))
            _tcs.update("telegram_allowed_ids", _allowed)
            console.print(f"  [green]✓[/green]  [dim]{_tval} added to allowlist[/dim]")
        else:
            console.print(f"  [yellow]![/yellow]  [dim]{_tval} already in allowlist[/dim]")
    elif _tsub == "remove" and _tval:
        _allowed = _tcs.load().get("telegram_allowed_ids", [])
        _new = [i for i in _allowed if str(i) != str(_tval)]
        _tcs.update("telegram_allowed_ids", _new)
        console.print(f"  [green]✓[/green]  [dim]{_tval} removed[/dim]")
    elif _tsub == "list":
        _allowed = _tcs.load().get("telegram_allowed_ids", [])
        if _allowed:
            console.print()
            for _tid in _allowed:
                console.print(f"  [cyan]{_tid}[/cyan]")
            console.print()
        else:
            console.print("  [dim]Allowlist empty — onboarding mode (all allowed)[/dim]")
    else:
        _cfg2       = _tcs.load()
        _tok        = _cfg2.get("telegram_token", "")
        _tok_legacy = ""
        try:
            _tf = Path.home() / ".aion_telegram_token"
            if _tf.is_file(): _tok_legacy = _tf.read_text().strip()
        except Exception: pass
        _active_tok = _tok or _tok_legacy
        _allowed    = _cfg2.get("telegram_allowed_ids", [])
        console.print()
        console.print(f"  [dim]Token:[/dim]     {'[green]set[/green] (' + _active_tok[:12] + '…)' if _active_tok else '[red]not set[/red]'}")
        console.print(f"  [dim]Allowlist:[/dim] {len(_allowed)} IDs" if _allowed else "  [dim]Allowlist:[/dim] [dim]empty (onboarding mode)[/dim]")
        console.print()
        console.print("  [dim]/telegram token <token>  |  add <id>  |  remove <id>  |  list[/dim]")
        console.print()


_CMD_PREFIX_DISPATCH: list[tuple[str, object]] = [
    ("/config",    _cmd_config),
    ("/snapshots", _cmd_snapshots),
    ("/plugins",   _cmd_plugins),
    ("/telegram",  _cmd_telegram),
]


# ── main loop ─────────────────────────────────────────────────────────────────

async def main() -> None:
    console.print()

    # ── First-time setup (runs before aion import so init_defaults() respects choices) ──
    try:
        from plugin_loader import DISABLED_FILE
        if not DISABLED_FILE.exists():
            _run_setup()
    except Exception:
        pass  # if plugin_loader not available, skip silently

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
                    "[cyan]/plugins[/cyan]        Plugins: /plugins [enable|disable <name>]",
                    "[cyan]/telegram[/cyan]       Telegram: /telegram [token <tok>|add <id>|remove <id>|list]",
                    "[cyan]/snapshots[/cyan]      Snapshots: /snapshots [<plugin>] [restore <plugin> [<ts>]]",
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

        dispatched = False
        for _prefix, _handler in _CMD_PREFIX_DISPATCH:
            if cmd.startswith(_prefix):
                _handler(user_input, _aion)
                dispatched = True
                break
        if dispatched:
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
