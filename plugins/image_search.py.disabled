from playwright.sync_api import sync_playwright
import random

def register(api):
    api.register_tool(
        name="image_search",
        description="Sucht Bilder zu einem Begriff via DuckDuckGo und gibt direkte Bild-URLs zurück. Nutze dieses Tool wenn der Nutzer ein Bild sehen möchte, du einen Sachverhalt visuell illustrieren willst, oder wenn nach Fotos, Logos, Diagrammen gefragt wird. Englische Suchbegriffe liefern bessere Ergebnisse.",
        func=search_images_playwright,
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Suchanfrage (Englisch empfohlen für beste Ergebnisse)"
                },
                "count": {
                    "type": "integer",
                    "description": "Anzahl der Bilder (1–10, Standard: 3)",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    )

def search_images_playwright(query: str, count: int = 3) -> dict:
    """
    Sucht Bilder mit Playwright, um eine Blockade durch DuckDuckGo zu umgehen.
    """
    images = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            
            url = f"https://duckduckgo.com/?q={query}&t=h_&iar=images&iax=images&ia=images"
            page.goto(url, wait_until='networkidle', timeout=15000)

            # Scrollen, um mehr Bilder zu laden (optional, aber oft nützlich)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

            # Extrahiere Bild-URLs und Titel
            image_elements = page.query_selector_all('.tile--img__img')
            
            # Manchmal sind die Bilder in 'data-src', manchmal in 'src'
            for el in image_elements[:count]:
                src = el.get_attribute('data-src') or el.get_attribute('src')
                if src and src.startswith('http'):
                    # Korrigiere die URL, falls sie mit // beginnt
                    if src.startswith('//'):
                        src = 'https:' + src
                    
                    images.append({
                        "url": src,
                        "title": el.get_attribute('alt') or query
                    })

            browser.close()
            
            if not images:
                return {"ok": False, "error": "Keine Bilder gefunden oder Selektoren haben sich geändert."}

        return {"ok": True, "images": images}

    except Exception as e:
        error_message = f"Ein Fehler ist bei der Playwright-Bildersuche aufgetreten: {str(e)}"
        print(error_message) # Log to console
        return {"ok": False, "error": error_message}
