import requests
import json

# Globale Variablen für die API-Basis-URL und den Pfad zur Konfigurationsdatei
API_BASE_URL = "https://www.moltbook.com/api/v1"
CONFIG_PATH = "moltbook_credentials.json"
AION_API = None

def register_agent(name: str, description: str) -> dict:
    """
    Registriert einen neuen Agenten auf Moltbook.
    Gibt die Server-Antwort zurück, die api_key, claim_url und verification_code enthält.
    """
    url = f"{API_BASE_URL}/agents/register"
    payload = {
        "name": name,
        "description": description
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()  # Wirft eine Exception bei HTTP-Fehlern
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Netzwerk- oder HTTP-Fehler: {str(e)}"}

def _get_api_key():
    """Lädt den API-Schlüssel aus der Konfigurationsdatei."""
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f).get("api_key")
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def check_claim_status() -> dict:
    """Überprüft den Verifizierungsstatus des Agenten auf Moltbook."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "API-Schlüssel nicht gefunden. Bitte zuerst registrieren."}
    
    url = f"{API_BASE_URL}/agents/status"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Netzwerk- oder HTTP-Fehler: {str(e)}"}

def create_post(title: str, submolt_name: str, content: str) -> dict:
    """Erstellt einen neuen Beitrag (Post) auf Moltbook."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "API-Schlüssel nicht gefunden. Bitte zuerst registrieren."}
        
    url = f"{API_BASE_URL}/posts"
    payload = {
        "title": title,
        "submolt_name": submolt_name,
        "content": content
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        # Versuche, detailliertere Fehlerinformationen aus der Antwort zu extrahieren
        error_details = str(e)
        try:
            if e.response is not None:
                error_details = e.response.json()
        except json.JSONDecodeError:
            pass # Behalte den ursprünglichen Fehlerstring, wenn JSON-Dekodierung fehlschlägt
        return {"error": f"Netzwerk- oder HTTP-Fehler: {error_details}"}

def register(api):
    """
    Registriert die Moltbook-Tools bei der AION-API.
    """
    global AION_API
    AION_API = api
    
    # Tool: register_agent
    register_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Der Name des Agenten, z.B. 'AION'."
            },
            "description": {
                "type": "string",
                "description": "Eine kurze Beschreibung des Agenten und seiner Fähigkeiten."
            }
        },
        "required": ["name", "description"]
    }
    api.register_tool(
        name="moltbook_register_agent",
        description="Registriert diesen Agenten auf der sozialen Plattform Moltbook.",
        func=register_agent,
        input_schema=register_schema
    )

    # Tool: check_claim_status
    api.register_tool(
        name="moltbook_check_claim_status",
        description="Überprüft den Verifizierungsstatus des Agenten auf Moltbook.",
        func=check_claim_status,
        input_schema={"type": "object", "properties": {}}
    )

    # Tool: create_post
    post_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Der Titel des Beitrags."
            },
            "submolt_name": {
                "type": "string",
                "description": "Der Name des Submolts (Channel), in dem gepostet werden soll (z.B. 'general')."
            },
            "content": {
                "type": "string",
                "description": "Der Inhalt des Beitrags, der auf Moltbook veröffentlicht werden soll."
            }
        },
        "required": ["title", "submolt_name", "content"]
    }
    api.register_tool(
        name="moltbook_create_post",
        description="Erstellt einen neuen Beitrag (Post) auf Moltbook.",
        func=create_post,
        input_schema=post_schema
    )