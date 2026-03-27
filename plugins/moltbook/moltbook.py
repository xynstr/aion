import requests
import json
from pathlib import Path

# Globale Variablen für die API-Basis-URL und den Pfad zur Configurationsdatei
API_BASE_URL = "https://www.moltbook.com/api/v1"
# Absolute path so it works regardless of cwd
CONFIG_PATH = Path(__file__).parent / "moltbook_credentials.json"
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
        response.raise_for_status()  # Wirft eine Exception bei HTTP-Errorn
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Netzwerk- oder HTTP-Error: {str(e)}"}

def _get_api_key() -> str:
    """Load the Moltbook API key.

    Priority:
      1. Encrypted vault  — credential_write("moltbook", "- api_key: ...")
      2. moltbook_credentials.json  (legacy plain-text fallback)
    """
    # 1. Vault (encrypted, preferred)
    try:
        from plugins.credentials.credentials import _vault_read_key_sync
        key = _vault_read_key_sync("moltbook", "api_key")
        if key:
            return key
    except Exception:
        pass
    # 2. Legacy JSON file fallback
    try:
        return json.loads(Path(CONFIG_PATH).read_text(encoding="utf-8")).get("api_key", "")
    except (FileNotFoundError, json.JSONDecodeError):
        return ""

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
        return {"error": f"Netzwerk- oder HTTP-Error: {str(e)}"}

def create_post(title: str, submolt_name: str, content: str) -> dict:
    """Creates einen neuen Beitrag (Post) auf Moltbook."""
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
        # Versuche, detailliertere Errorinformationen aus der Antwort zu extrahieren
        error_details = str(e)
        try:
            if e.response is not None:
                error_details = e.response.json()
        except json.JSONDecodeError:
            pass # Behalte den ursprünglichen Errorstring, wenn JSON-Dekodierung fehlschlägt
        return {"error": f"Netzwerk- oder HTTP-Error: {error_details}"}

def get_own_posts(limit: int = 25, cursor: str = None) -> dict:
    """Ruft die eigenen Posts des authentifizierten Agenten von Moltbook ab."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "API-Schlüssel nicht gefunden."}

    url = f"{API_BASE_URL}/agents/me/posts"
    params: dict = {"limit": limit}
    if cursor:
        params["cursor"] = cursor

    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Netzwerk- oder HTTP-Error: {str(e)}"}


def get_feed(submolt_name: str = None, sort: str = "new", limit: int = 25, cursor: str = None) -> dict:
    """Ruft einen Feed von Posts ab, optional gefiltert nach Submolt."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "API-Schlüssel nicht gefunden."}
    
    url = f"{API_BASE_URL}/posts"
    params = {
        "sort": sort,
        "limit": limit
    }
    if submolt_name:
        params["submolt_name"] = submolt_name
    if cursor:
        params["cursor"] = cursor
        
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Netzwerk- oder HTTP-Error: {str(e)}"}

def add_comment(post_id: str, content: str) -> dict:
    """Fügt einen Kommentar zu einem bestimmten Post hinzu."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "API-Schlüssel nicht gefunden."}

    url = f"{API_BASE_URL}/posts/{post_id}/comments"
    payload = {"content": content}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Netzwerk- oder HTTP-Error: {str(e)}"}

def verify_action(verification_code: str, answer: str) -> dict:
    """Sendet die Antwort auf eine Verifizierungs-Challenge."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "API-Schlüssel nicht gefunden."}

    url = f"{API_BASE_URL}/verify"
    payload = {
        "verification_code": verification_code,
        "answer": answer
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
        return {"error": f"Netzwerk- oder HTTP-Error: {str(e)}"}


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
                "description": "Der Name des Submolts (Channel), in dem gepostet werden soll (z.B. 'general'). WICHTIG: Der Parameter heißt 'submolt_name', NICHT 'submolt'."
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
        description="Erstellt einen neuen Beitrag (Post) auf Moltbook. Pflichtparameter: title, submolt_name (NICHT 'submolt'), content.",
        func=create_post,
        input_schema=post_schema
    )

    # Tool: get_own_posts
    own_posts_schema = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Anzahl der abzurufenden Posts (Standard: 25)."
            },
            "cursor": {
                "type": "string",
                "description": "Cursor für die Paginierung (aus der vorherigen Antwort)."
            }
        }
    }
    api.register_tool(
        name="moltbook_get_own_posts",
        description="Ruft die eigenen Posts des authentifizierten Agenten von Moltbook ab.",
        func=get_own_posts,
        input_schema=own_posts_schema
    )

    # Tool: get_feed
    feed_schema = {
        "type": "object",
        "properties": {
            "submolt_name": {
                "type": "string",
                "description": "Name des Submolts, dessen Feed abgerufen werden soll (optional)."
            },
            "sort": {
                "type": "string",
                "description": "Sortierreihenfolge: 'hot', 'new', 'top', 'rising' (Standard: 'new')."
            },
            "limit": {
                "type": "integer",
                "description": "Anzahl der abzurufenden Posts (Standard: 25)."
            },
            "cursor": {
                "type": "string",
                "description": "Cursor für die Paginierung (aus der vorherigen Antwort)."
            }
        }
    }
    api.register_tool(
        name="moltbook_get_feed",
        description="Ruft einen Feed von Posts von Moltbook ab.",
        func=get_feed,
        input_schema=feed_schema
    )

    # Tool: add_comment
    comment_schema = {
        "type": "object",
        "properties": {
            "post_id": {
                "type": "string",
                "description": "Die ID des Posts, zu dem der Kommentar hinzugefügt wird."
            },
            "content": {
                "type": "string",
                "description": "Der Inhalt des Kommentars."
            }
        },
        "required": ["post_id", "content"]
    }
    api.register_tool(
        name="moltbook_add_comment",
        description="Fügt einen Kommentar zu einem Moltbook-Post hinzu.",
        func=add_comment,
        input_schema=comment_schema
    )

    # Tool: verify_action
    verify_schema = {
        "type": "object",
        "properties": {
            "verification_code": {
                "type": "string",
                "description": "Der Verifizierungscode aus einer vorherigen API-Antwort."
            },
            "answer": {
                "type": "string",
                "description": "Die Antwort auf die Challenge (z.B. das Ergebnis einer Rechenaufgabe)."
            }
        },
        "required": ["verification_code", "answer"]
    }
    api.register_tool(
        name="moltbook_verify_action",
        description="Verifiziert eine Aktion (z.B. einen Kommentar) durch das Lösen einer Challenge.",
        func=verify_action,
        input_schema=verify_schema
    )