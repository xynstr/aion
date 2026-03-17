"""
AION Plugin: Image Search
=========================
Sucht Bilder via DuckDuckGo (primär) mit Playwright-Fallback.

Installation:
  pip install duckduckgo-search
  pip install playwright && playwright install chromium   # für Fallback
"""


def search_images(query: str, count: int = 3, **_) -> dict:
    """Sucht Bilder auf DuckDuckGo. Fallback: Playwright-Scraping."""
    # Primär: duckduckgo-search (schnell, kein Browser)
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=count))
        images = [
            {"url": r.get("image", ""), "title": r.get("title", query)}
            for r in results
            if r.get("image", "").startswith("http")
        ]
        if images:
            return {"ok": True, "images": images}
    except Exception:
        pass

    # Fallback: Playwright
    try:
        from playwright.sync_api import sync_playwright
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
                f"https://duckduckgo.com/?q={query}&iax=images&ia=images",
                wait_until="networkidle",
                timeout=15000,
            )
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

            images = []
            for el in page.query_selector_all('[data-testid="result-image-img"], .tile--img__img')[:count]:
                src = el.get_attribute("data-src") or el.get_attribute("src") or ""
                if src.startswith("//"):
                    src = "https:" + src
                if src.startswith("http"):
                    images.append({"url": src, "title": el.get_attribute("alt") or query})

            browser.close()

        if images:
            return {"ok": True, "images": images}
        return {"ok": False, "error": "Keine Bilder gefunden (DDG-Selektor evtl. veraltet)."}

    except Exception as e:
        return {"ok": False, "error": f"Bildsuche fehlgeschlagen: {e}"}


def register(api):
    api.register_tool(
        name="image_search",
        description=(
            "Sucht Bilder zu einem Begriff und gibt direkte Bild-URLs zurück. "
            "Nutze dieses Tool IMMER wenn der Nutzer ein Bild, Foto, Logo oder "
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
                    "description": "Anzahl der Bilder (1–10, Standard: 3)",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    )
    print("[Plugin] image_search geladen — DuckDuckGo + Playwright-Fallback aktiv.")
