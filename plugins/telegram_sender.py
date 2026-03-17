import requests
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str):
    """Sendet eine Nachricht an die gespeicherte Telegram-Chat-ID."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return "Telegram Bot Token oder Chat ID sind nicht in den Umgebungsvariablen gesetzt."
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return f"Nachricht an Telegram gesendet: {message}"
    except requests.exceptions.RequestException as e:
        return f"Fehler beim Senden der Telegram-Nachricht: {e}"

def register(api):
    """Registriert die Telegram-Funktion als AION-Tool."""
    input_schema = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Die zu sendende Nachricht."
            }
        },
        "required": ["message"]
    }
    api.register_tool(
        name="send_telegram_message",
        description="Sendet eine Nachricht an die gespeicherte Telegram-Chat-ID.",
        func=send_telegram_message,
        input_schema=input_schema
    )