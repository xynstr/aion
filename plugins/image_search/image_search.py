"""
AION Plugin: Image Search
=========================
Primär: Openverse API (kostenlos, kein Key, Creative Commons)
Fallback: DuckDuckGo-Search-Bibliothek
"""
import json
import urllib.request
import urllib.parse


def search_images(query: str, count: int = 3, **_) -> dict:
    """Sucht Bilder. Primär: Openverse API. Fallback: DDG."""

    # Primär: Openverse (freie CC-Bilder, kein API-Key nötig)
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

    # Fallback: DuckDuckGo
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
            return {"ok": True, "images": images, "source": "ddg"}
    except Exception:
        pass

    return {"ok": False, "error": f"Keine Bilder für '{query}' gefunden."}


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
    print("[Plugin] image_search geladen — Openverse (primär) + DDG (Fallback).")
