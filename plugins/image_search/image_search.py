"""
AION Plugin: Image Search via DuckDuckGo
=========================================
Synchrone Bildsuche mit duckduckgo-search (keine asyncio-Konflikte).

Installation:
  pip install duckduckgo-search

Nutzer können Bilder als Antworten includieren — wird in
AionSession.stream() in response_blocks ausgeliefert.
"""

def search_images(query: str, max_results: int = 3, **_) -> dict:
    """
    Sucht Bilder auf DuckDuckGo und gibt URLs zurück.

    Args:
        query: Suchbegriff (z.B. "sunset landscape")
        max_results: Anzahl der Bilder (default: 3)

    Returns:
        {"ok": True, "images": [{"url": "...", "title": "..."}, ...]}
        oder
        {"ok": False, "error": "..."}
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return {
            "ok": False,
            "error": "duckduckgo-search nicht installiert. "
                    "Installieren mit: pip install duckduckgo-search"
        }

    try:
        with DDGS() as ddgs:
            results = ddgs.images(query, max_results=max_results)

        images = []
        for img in results:
            try:
                images.append({
                    "url": img.get("image", ""),
                    "title": img.get("title", ""),
                    "source": img.get("source", ""),
                })
            except Exception:
                continue

        if not images:
            return {"ok": False, "error": f"Keine Bilder für '{query}' gefunden."}

        return {"ok": True, "images": images}

    except Exception as e:
        return {"ok": False, "error": f"Suchfehler: {str(e)}"}


def register(api):
    """Registriert das Image-Search-Tool bei AION."""
    api.register_tool(
        name="search_images",
        description=(
            "Sucht Bilder auf DuckDuckGo zu einem Suchbegriff. "
            "Gibt URLs zurück, die AION in Antworten einbinden kann. "
            "Nutze dies, um visuell angereicherte Antworten zu geben."
        ),
        func=search_images,
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Suchbegriff (z.B. 'sunset landscape', 'python programming')"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Anzahl der zu suchenden Bilder (default: 3, max: 10)",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10,
                }
            },
            "required": ["query"],
        },
    )
    print("[Plugin] image_search geladen — DuckDuckGo synchrone Bildsuche aktiv.")
