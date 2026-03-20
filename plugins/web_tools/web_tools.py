"""
web_tools — Web-Suche und -Abruf (web_search, web_fetch)

War früher hardcodiert in aion.py/_dispatch().
Als Plugin hot-reloadbar per self_reload_tools.
"""


def register(api):

    async def _web_search(query: str = "", max_results: int = 8, **_):
        import urllib.parse
        try:
            import httpx
        except ImportError:
            return {"error": "httpx nicht installiert. Bitte: pip install httpx"}

        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0"},
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

            return {"results": results, "query": query}
        except Exception as e:
            return {"error": str(e), "query": query}

    async def _web_fetch(url: str = "", timeout: int = 20, **_):
        try:
            import httpx
        except ImportError:
            return {"error": "httpx nicht installiert. Bitte: pip install httpx"}

        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0"},
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

            return {"url": url, "content": text[:8000], "status_code": r.status_code}
        except Exception as e:
            return {"error": str(e), "url": url}

    # ── Tool-Registrierungen ──────────────────────────────────────────────────

    api.register_tool(
        name="web_search",
        description="Sucht im Internet via DuckDuckGo.",
        func=_web_search,
        input_schema={
            "type": "object",
            "properties": {
                "query":       {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    )

    api.register_tool(
        name="web_fetch",
        description="Lädt den Textinhalt einer URL herunter.",
        func=_web_fetch,
        input_schema={
            "type": "object",
            "properties": {
                "url":     {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["url"],
        },
    )
