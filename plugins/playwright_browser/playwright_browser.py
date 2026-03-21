"""
AION Plugin: Playwright Browser Control
========================================
Steuert einen Chromium-Browser per AION-Tools.
Läuft synchron (sync_playwright) in run_in_executor — kein Konflikt mit dem
AION-Asyncio-Loop.

Einmalige Einrichtung:
    pip install playwright
    playwright install chromium

Konfiguration (config.json, optional):
    "browser_headless": true    # false = sichtbares Browserfenster
"""

import atexit
import base64
import json
import os
import threading
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Browser, Page, Playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

_BOT_DIR = Path(__file__).parent.parent.parent

# ── Singleton Browser-State ────────────────────────────────────────────────────

_pw:      "Playwright | None" = None
_browser: "Browser | None"   = None
_page:    "Page | None"       = None
_lock = threading.Lock()


def _is_headless() -> bool:
    try:
        cfg = json.loads((_BOT_DIR / "config.json").read_text(encoding="utf-8"))
        return bool(cfg.get("browser_headless", True))
    except Exception:
        return True


def _ensure_browser() -> "Page":
    """Gibt immer eine gültige Page zurück. Thread-safe."""
    global _pw, _browser, _page
    with _lock:
        if _browser is None or not _browser.is_connected():
            if _pw is not None:
                try:
                    _pw.stop()
                except Exception:
                    pass
            _pw      = sync_playwright().start()
            _browser = _pw.chromium.launch(headless=_is_headless())
        if _page is None or _page.is_closed():
            _page = _browser.new_page()
    return _page


def _shutdown():
    global _browser, _pw, _page
    try:
        if _page and not _page.is_closed():
            _page.close()
        if _browser:
            _browser.close()
        if _pw:
            _pw.stop()
    except Exception:
        pass
    _page = _browser = _pw = None


atexit.register(_shutdown)


# ── Tool-Funktionen (alle synchron) ────────────────────────────────────────────

def browser_open(url: str = "", **_) -> dict:
    """Lädt eine URL im Browser. Gibt Titel und finale URL zurück."""
    if not url:
        return {"error": "Keine URL angegeben."}
    try:
        page = _ensure_browser()
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        return {"ok": True, "url": page.url, "title": page.title()}
    except Exception as e:
        return {"error": str(e)}


def browser_screenshot(**_) -> dict:
    """Screenshot der aktuellen Seite als base64-PNG."""
    try:
        page = _ensure_browser()
        data = page.screenshot(type="png")
        b64  = base64.b64encode(data).decode()
        return {
            "ok":    True,
            "image": f"data:image/png;base64,{b64}",
            "url":   page.url,
            "title": page.title(),
        }
    except Exception as e:
        return {"error": str(e)}


def browser_click(selector: str = "", **_) -> dict:
    """Klickt ein Element per CSS-Selektor oder Text."""
    if not selector:
        return {"error": "Kein Selektor angegeben."}
    try:
        page = _ensure_browser()
        page.click(selector, timeout=10_000)
        return {"ok": True, "clicked": selector, "url": page.url}
    except Exception as e:
        return {"error": str(e), "selector": selector}


def browser_fill(selector: str = "", value: str = "", **_) -> dict:
    """Befüllt ein Eingabefeld (Input/Textarea) per CSS-Selektor."""
    if not selector:
        return {"error": "Kein Selektor angegeben."}
    try:
        page = _ensure_browser()
        page.fill(selector, value, timeout=10_000)
        return {"ok": True, "selector": selector, "value": value}
    except Exception as e:
        return {"error": str(e)}


def browser_get_text(**_) -> dict:
    """Gibt den sichtbaren Textinhalt der aktuellen Seite zurück (max. 10.000 Zeichen)."""
    try:
        page = _ensure_browser()
        text = page.inner_text("body")
        truncated = len(text) > 10_000
        return {
            "ok":        True,
            "url":       page.url,
            "title":     page.title(),
            "text":      text[:10_000],
            "truncated": truncated,
        }
    except Exception as e:
        return {"error": str(e)}


def browser_evaluate(js: str = "", **_) -> dict:
    """Führt JavaScript auf der aktuellen Seite aus und gibt das Ergebnis zurück."""
    if not js:
        return {"error": "Kein JS angegeben."}
    try:
        page   = _ensure_browser()
        result = page.evaluate(js)
        try:
            serialized = json.dumps(result)
        except Exception:
            serialized = str(result)
        return {"ok": True, "result": serialized}
    except Exception as e:
        return {"error": str(e)}


def browser_find(selector: str = "", **_) -> dict:
    """Sucht Elemente per CSS-Selektor. Gibt Anzahl + erste 5 Texte zurück."""
    if not selector:
        return {"error": "Kein Selektor angegeben."}
    try:
        page     = _ensure_browser()
        elements = page.query_selector_all(selector)
        count    = len(elements)
        samples  = []
        for el in elements[:5]:
            try:
                samples.append(el.inner_text()[:200])
            except Exception:
                samples.append("[kein Text]")
        return {"ok": True, "count": count, "selector": selector, "samples": samples}
    except Exception as e:
        return {"error": str(e)}


def browser_close(**_) -> dict:
    """Schließt die aktuelle Browser-Seite."""
    global _page
    try:
        with _lock:
            if _page and not _page.is_closed():
                _page.close()
            _page = None
        return {"ok": True, "message": "Browser-Seite geschlossen."}
    except Exception as e:
        return {"error": str(e)}


# ── Register ───────────────────────────────────────────────────────────────────

def register(api):
    if not HAS_PLAYWRIGHT:
        print("[playwright_browser] 'playwright' nicht installiert.")
        print("  Bitte ausführen: pip install playwright && playwright install chromium")
        return

    api.register_tool(
        name="browser_open",
        description="Lädt eine URL im Browser. Gibt Titel und finale URL zurück.",
        func=browser_open,
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Die URL die geöffnet werden soll."}
            },
            "required": ["url"],
        },
    )
    api.register_tool(
        name="browser_screenshot",
        description="Macht einen Screenshot der aktuellen Browser-Seite. Gibt Base64-PNG zurück.",
        func=browser_screenshot,
        input_schema={"type": "object", "properties": {}},
    )
    api.register_tool(
        name="browser_click",
        description="Klickt ein Element auf der Seite per CSS-Selektor (z.B. 'button#submit', 'a.link', 'text=Anmelden').",
        func=browser_click,
        input_schema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS-Selektor oder Playwright-Locator des Elements."}
            },
            "required": ["selector"],
        },
    )
    api.register_tool(
        name="browser_fill",
        description="Befüllt ein Eingabefeld (Input/Textarea) per CSS-Selektor mit einem Wert.",
        func=browser_fill,
        input_schema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS-Selektor des Eingabefelds."},
                "value":    {"type": "string", "description": "Der einzugebende Wert."},
            },
            "required": ["selector", "value"],
        },
    )
    api.register_tool(
        name="browser_get_text",
        description="Gibt den sichtbaren Text der aktuellen Seite zurück (max. 10.000 Zeichen). Nützlich zum Lesen von Seiteninhalten.",
        func=browser_get_text,
        input_schema={"type": "object", "properties": {}},
    )
    api.register_tool(
        name="browser_evaluate",
        description="Führt JavaScript auf der aktuellen Seite aus und gibt das Ergebnis zurück.",
        func=browser_evaluate,
        input_schema={
            "type": "object",
            "properties": {
                "js": {"type": "string", "description": "Der auszuführende JavaScript-Code."}
            },
            "required": ["js"],
        },
    )
    api.register_tool(
        name="browser_find",
        description="Sucht Elemente auf der Seite per CSS-Selektor. Gibt Anzahl und erste 5 Texte zurück.",
        func=browser_find,
        input_schema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS-Selektor der zu suchenden Elemente."}
            },
            "required": ["selector"],
        },
    )
    api.register_tool(
        name="browser_close",
        description="Schließt die aktuelle Browser-Seite.",
        func=browser_close,
        input_schema={"type": "object", "properties": {}},
    )

    print("[playwright_browser] ✓ 8 Browser-Tools registriert.")
