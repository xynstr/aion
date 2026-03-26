"""
AION Updater Plugin — Täglicher GitHub-Release-Check
=====================================================
Prüft einmal täglich ob eine neue Version auf GitHub verfügbar ist.
Bei einer neuen Version werden alle aktiven Kanäle benachrichtigt
(Telegram, Discord, Slack) und der Status über /api/update-status
im Web-UI angezeigt.

Konfiguration (.env):
  AION_GITHUB_REPO=owner/repo-name   z.B. "myuser/aion"
"""

import os
import re
import sys
import threading
import time
import datetime
from pathlib import Path

# ── Konfiguration ─────────────────────────────────────────────────────────────

_GITHUB_REPO        = os.environ.get("AION_GITHUB_REPO", "xynstr/aion").strip()
_FIRST_CHECK_DELAY  = 60        # Sekunden nach Start bis zum ersten Check
_CHECK_INTERVAL_H   = 24        # Stunden zwischen den Checks
_AION_DIR           = Path(__file__).parent.parent.parent

_update_state: dict = {
    "current_version":  None,
    "latest_version":   None,
    "update_available": False,
    "release_url":      None,
    "release_notes":    None,
    "last_checked":     None,
    "error":            None,
}
_notified_version: str | None = None   # verhindert Mehrfach-Benachrichtigung


# ── Versions-Hilfsfunktionen ──────────────────────────────────────────────────

def _get_local_version() -> str:
    """Liest die Version aus pyproject.toml (Python-3.11-tomllib oder Regex-Fallback)."""
    toml = _AION_DIR / "pyproject.toml"
    if not toml.is_file():
        return "0.0.0"
    text = toml.read_text(encoding="utf-8")
    try:
        import tomllib  # Python 3.11+
        data = tomllib.loads(text)
        return data.get("project", {}).get("version", "0.0.0")
    except ImportError:
        pass
    try:
        import tomli  # pip install tomli
        data = tomli.loads(text)
        return data.get("project", {}).get("version", "0.0.0")
    except ImportError:
        pass
    m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else "0.0.0"


def _parse_version(v: str) -> tuple:
    """Konvertiert '1.2.3' → (1, 2, 3) für numerischen Vergleich."""
    v = v.lstrip("v").strip()
    parts = re.split(r"[.\-]", v)
    result = []
    for p in parts[:4]:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    while len(result) < 3:
        result.append(0)
    return tuple(result)


# ── GitHub API ────────────────────────────────────────────────────────────────

def _fetch_latest_release() -> dict | None:
    """Holt das neueste Release von der GitHub API. Gibt None bei Fehler zurück."""
    if not _GITHUB_REPO:
        return None
    url = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"
    try:
        import httpx
        r = httpx.get(url, timeout=10, headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            _update_state["error"] = f"Repo '{_GITHUB_REPO}' nicht gefunden oder keine Releases."
        else:
            _update_state["error"] = f"GitHub API Fehler: {r.status_code}"
        return None
    except Exception as e:
        _update_state["error"] = str(e)
        return None


# ── Kanal-Benachrichtigungen ──────────────────────────────────────────────────

def _notify_telegram(msg: str):
    token_file  = Path.home() / ".aion_telegram_token"
    chatid_file = Path.home() / ".aion_telegram_chatid"
    token  = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token and token_file.is_file():
        token = token_file.read_text().strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id and chatid_file.is_file():
        chat_id = chatid_file.read_text().strip()
    if not token or not chat_id:
        return
    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg},
            timeout=10,
        )
    except Exception as e:
        print(f"[Updater] Telegram-Benachrichtigung fehlgeschlagen: {e}", flush=True)


def _notify_discord(msg: str):
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        # Fallback: Webhook-URL aus config.json lesen
        try:
            import json
            cfg = json.loads((_AION_DIR / "config.json").read_text(encoding="utf-8"))
            webhook = cfg.get("discord_webhook_url", "").strip()
        except Exception:
            pass
    if not webhook:
        return
    try:
        import httpx
        httpx.post(webhook, json={"content": msg}, timeout=10)
    except Exception as e:
        print(f"[Updater] Discord-Benachrichtigung fehlgeschlagen: {e}", flush=True)


def _notify_slack(msg: str):
    token      = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    channel_id = os.environ.get("SLACK_CHANNEL_ID", "").strip()
    if not token or not channel_id:
        return
    try:
        import httpx
        httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": channel_id, "text": msg},
            timeout=10,
        )
    except Exception as e:
        print(f"[Updater] Slack-Benachrichtigung fehlgeschlagen: {e}", flush=True)


def _notify_all_channels():
    global _notified_version
    latest  = _update_state["latest_version"]
    current = _update_state["current_version"]
    url     = _update_state["release_url"] or ""

    if latest == _notified_version:
        return   # bereits gemeldet
    _notified_version = latest

    msg = (
        f"🆕 AION Update verfügbar!\n"
        f"Aktuelle Version: {current}\n"
        f"Neue Version:     {latest}\n"
        f"Update ausführen: aion update\n"
        f"{url}"
    ).strip()

    for notify in (_notify_telegram, _notify_discord, _notify_slack):
        try:
            notify(msg)
        except Exception:
            pass


# ── Check-Logik ───────────────────────────────────────────────────────────────

def _check_once():
    """Führt einen einmaligen Update-Check durch und aktualisiert _update_state."""
    if not _GITHUB_REPO:
        _update_state["error"] = "AION_GITHUB_REPO nicht gesetzt — Update-Check deaktiviert."
        return

    data = _fetch_latest_release()
    _update_state["last_checked"] = datetime.datetime.now().isoformat()

    if data is None:
        return

    tag     = data.get("tag_name", "")
    latest  = tag.lstrip("v").strip()
    current = _update_state["current_version"] or _get_local_version()

    _update_state["latest_version"]  = latest
    _update_state["release_url"]     = data.get("html_url", "")
    _update_state["release_notes"]   = (data.get("body") or "")[:500]
    _update_state["current_version"] = current
    _update_state["error"]           = None

    if latest and _parse_version(latest) > _parse_version(current):
        _update_state["update_available"] = True
        print(
            f"[Updater] Neue Version verfügbar: {latest} (aktuell: {current})"
            f" — 'aion update' ausführen",
            flush=True,
        )
        _notify_all_channels()
    else:
        _update_state["update_available"] = False
        print(f"[Updater] Kein Update. Aktuelle Version {current} ist aktuell.", flush=True)


def _updater_loop():
    time.sleep(_FIRST_CHECK_DELAY)
    while True:
        try:
            _check_once()
        except Exception as e:
            _update_state["error"] = str(e)
        time.sleep(_CHECK_INTERVAL_H * 3600)


# ── FastAPI Router ─────────────────────────────────────────────────────────────

def _build_router():
    try:
        from fastapi import APIRouter
        from fastapi.responses import JSONResponse
    except ImportError:
        return None

    router = APIRouter()

    @router.get("/api/update-status")
    async def update_status():
        return JSONResponse(_update_state)

    @router.post("/api/update-trigger")
    async def update_trigger():
        """Erzwingt sofortigen Update-Check (für Tests / manuelle Auslösung)."""
        import asyncio
        asyncio.get_running_loop().run_in_executor(None, _check_once)
        return JSONResponse({"ok": True, "message": "Update-Check gestartet"})

    return router


# ── Plugin-Registration ────────────────────────────────────────────────────────

def register(api):
    # Version einmalig einlesen
    _update_state["current_version"] = _get_local_version()

    # Verhindere Mehrfach-Start
    for t in threading.enumerate():
        if t.name == "aion-updater":
            _register_tools(api)
            _register_router(api)
            return

    t = threading.Thread(target=_updater_loop, daemon=True, name="aion-updater")
    t.start()

    repo_info = f"Repo: {_GITHUB_REPO}" if _GITHUB_REPO else "AION_GITHUB_REPO nicht gesetzt"
    print(
        f"[Plugin] updater geladen — {repo_info}"
        f" | Check alle {_CHECK_INTERVAL_H}h (erster Check in {_FIRST_CHECK_DELAY}s)",
        flush=True,
    )

    _register_tools(api)
    _register_router(api)


def _register_tools(api):
    import json as _json

    def get_update_status(**_) -> dict:
        """Gibt den aktuellen Update-Status zurück."""
        return dict(_update_state)

    api.register_tool(
        name="update_status",
        description="Gibt zurück ob eine neue AION-Version verfügbar ist, inkl. Versionsnummern und Release-URL.",
        func=get_update_status,
        input_schema={"type": "object", "properties": {}},
    )

    def trigger_update_check(**_) -> dict:
        """Triggert einen sofortigen GitHub-Versions-Check."""
        _check_once()
        return dict(_update_state)

    api.register_tool(
        name="check_for_updates",
        description="Prüft sofort ob eine neue AION-Version auf GitHub verfügbar ist.",
        func=trigger_update_check,
        input_schema={"type": "object", "properties": {}},
    )


def _register_router(api):
    router = _build_router()
    if router is not None:
        api.register_router(router, prefix="", tags=["updater"])
