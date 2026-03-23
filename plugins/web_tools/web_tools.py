"""
web_tools — Web-Suche und -Abruf (web_search, web_fetch)

Suche: ddgs-Bibliothek (primär) → httpx-Scraping (Fallback)
DuckDuckGo HTML-Endpoint blockiert Bot-Requests seit 2024; ddgs umgeht das korrekt.
"""


def register(api):

    async def _web_search(query: str = "", max_results: int = 8, **_):
        import asyncio

        # Primär: ddgs-Bibliothek
        try:
            from ddgs import DDGS

            def _sync_search():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=int(max_results)))

            raw = await asyncio.to_thread(_sync_search)
            results = [
                {
                    "title":   r.get("title", ""),
                    "url":     r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw
            ]
            return {"results": results, "query": query}

        except ImportError:
            pass  # Fallback unten

        # Fallback: httpx + BeautifulSoup (funktioniert nur noch eingeschränkt)
        import urllib.parse
        try:
            import httpx
        except ImportError:
            return {"error": "Weder 'ddgs' noch 'httpx' installiert. Bitte: pip install ddgs"}

        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                follow_redirects=True,
                timeout=20.0,
            ) as hc:
                r    = await hc.get(ddg_url)
                html = r.text

            results = []
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for div in soup.select(".result__body")[:int(max_results)]:
                    a    = div.select_one("a.result__a")
                    snip = div.select_one(".result__snippet")
                    if a:
                        results.append({
                            "title":   a.get_text(strip=True),
                            "url":     a.get("href", ""),
                            "snippet": snip.get_text(strip=True) if snip else "",
                        })
            except ImportError:
                pass

            if not results:
                return {"error": "Keine Ergebnisse. Bitte 'pip install ddgs' ausführen.", "query": query}

            return {"results": results, "query": query}
        except Exception as e:
            return {"error": str(e), "query": query}

    async def _web_fetch(url: str = "", timeout: int = 20, **_):
        try:
            import httpx
        except ImportError:
            return {"error": "httpx not installed. Bitte: pip install httpx"}

        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                follow_redirects=True,
                timeout=float(timeout),
            ) as hc:
                r    = await hc.get(url)
                text = r.text

            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
            except ImportError:
                pass

            # Dynamisches Limit basierend auf aktivem Modell
            try:
                import sys
                aion = sys.modules.get("aion")
                limit = aion._get_read_limit() if aion and hasattr(aion, "_get_read_limit") else 20_000
            except Exception:
                limit = 20_000

            return {"url": url, "content": text[:limit], "status_code": r.status_code}
        except Exception as e:
            return {"error": str(e), "url": url}

    # ── Tool-Registrierungen ──────────────────────────────────────────────────

    api.register_tool(
        name="web_search",
        description=(
            "Sucht im Internet via DuckDuckGo. "
            "Gibt Titel, URL und Snippet zurück. Nutze web_fetch für den vollen Seiteninhalt."
        ),
        func=_web_search,
        input_schema={
            "type": "object",
            "properties": {
                "query":       {"type": "string", "description": "Suchanfrage"},
                "max_results": {"type": "integer", "description": "Anzahl Ergebnisse (default 8)"},
            },
            "required": ["query"],
        },
    )

    api.register_tool(
        name="web_fetch",
        description="Lädt den Textinhalt einer URL herunter und gibt ihn bereinigt zurück.",
        func=_web_fetch,
        input_schema={
            "type": "object",
            "properties": {
                "url":     {"type": "string", "description": "URL zum Abrufen"},
                "timeout": {"type": "integer", "description": "Timeout in Sekunden (default 20)"},
            },
            "required": ["url"],
        },
    )
