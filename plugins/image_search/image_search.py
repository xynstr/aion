"""
AION Plugin: Image Search
=========================
Primär:  Openverse API (kostenlos, kein Key, sofort)
Fallback: Bing Images via Playwright (headless Chromium)
"""
import json
import urllib.request
import urllib.parse


def search_images(query: str, count: int = 1, **_) -> dict:
    """Searches Bilder. Primär: Openverse API. Fallback: Bing via Playwright."""

    # Primär: Openverse (freie CC-Bilder, kein API-Key, kein Browser)
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.openverse.org/v1/images/?q={encoded}&page_size={min(count, 20)}"
        req = urllib.request.Request(url, headers={"User-Agent": "AION-ImageSearch/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        images = [
            {"url": item["url"], "title": item.get("title") or query}
            for item in data.get("results", [])
            if item.get("url", "").startswith("http")
        ][:count]
        if images:
            return {"ok": True, "images": images, "source": "openverse"}
    except Exception:
        pass

    # Fallback: Bing Images via Playwright (headless Chromium)
    try:
        from playwright.sync_api import sync_playwright

        encoded = urllib.parse.quote(query)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page.goto(
                f"https://www.bing.com/images/search?q={encoded}&form=HDRSC2",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            page.wait_for_timeout(1500)

            images = []
            for el in page.query_selector_all("img.mimg")[:count * 2]:
                src = el.get_attribute("src") or el.get_attribute("data-src") or ""
                alt = el.get_attribute("alt") or query
                if src.startswith("http") and len(images) < count:
                    images.append({"url": src, "title": alt})

            browser.close()

        if images:
            return {"ok": True, "images": images, "source": "bing"}
    except Exception as e:
        return {"ok": False, "error": f"Bildsuche fehlgeschlagen: {e}"}

    return {"ok": False, "error": f"Keine Bilder für '{query}' gefunden."}


def register(api):
    api.register_tool(
        name="image_search",
        description=(
            "Sucht Bilder zu einem Begriff und gibt direkte Bild-URLs zurück. "
            "Nutze dieses Tool IMMER wenn der User ein Bild, Foto, Logo oder "
            "visuelle Inhalte sehen möchte. Englische Suchbegriffe empfohlen. "
            "Schreibe KEINE Markdown-Bild-Syntax — das System zeigt die Bilder automatisch."
        ),
        func=search_images,
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Suchanfrage auf Englisch (z.B. 'Homer Simpson photo')",
                },
                "count": {
                    "type": "integer",
                    "description": "Anzahl der Bilder (1–10, Standard: 1)",
                    "default": 1,
                },
            },
            "required": ["query"],
        },
    )
    print("[Plugin] image_search loaded — Openverse (primary) + Bing/Playwright (fallback).")
