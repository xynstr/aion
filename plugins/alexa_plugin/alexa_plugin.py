import logging
from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)
router = APIRouter()


def build_alexa_response(text: str, should_end_session: bool = False) -> dict:
    """Baut eine Standard-Antwort im Alexa-JSON-Format."""
    return {
        "version": "1.0",
        "response": {
            "outputSpeech": {"type": "PlainText", "text": text},
            "card": {"type": "Simple", "title": "AION", "content": text},
            "shouldEndSession": should_end_session,
        },
    }


@router.post("/api/alexa")
async def handle_alexa_request(request: Request):
    """Empfängt Alexa-Skill-Anfragen, leitet sie an AionSession weiter."""
    try:
        data = await request.json()
    except Exception:
        return build_alexa_response("Ungültige Anfrage.")

    request_type = data.get("request", {}).get("type", "")

    if request_type == "LaunchRequest":
        return build_alexa_response("AION ist bereit. Was kann ich für dich tun?")

    elif request_type == "IntentRequest":
        intent_name = data.get("request", {}).get("intent", {}).get("name", "")

        if intent_name == "AionCommandIntent":
            query = (
                data.get("request", {})
                .get("intent", {})
                .get("slots", {})
                .get("command", {})
                .get("value", "")
            )
            if not query:
                return build_alexa_response("Ich habe deinen Befehl nicht verstanden.")

            try:
                import aion
                session = aion.AionSession(channel="alexa")
                response_parts = []
                async for event in session.stream(query):
                    if event.get("type") == "token":
                        response_parts.append(event.get("content", ""))
                    elif event.get("type") in ("done", "error"):
                        break
                response_text = "".join(response_parts).strip()
                if not response_text:
                    response_text = "Ich habe die Aufgabe erledigt."
            except Exception as e:
                logger.error(f"AionSession Fehler: {e}", exc_info=True)
                response_text = "Entschuldigung, ein interner Fehler ist aufgetreten."

            return build_alexa_response(response_text)

        elif intent_name == "AMAZON.HelpIntent":
            return build_alexa_response("Sage zum Beispiel: Frage AION, wie das Wetter wird.")

        elif intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            return build_alexa_response("Auf Wiedersehen.", should_end_session=True)

        else:
            return build_alexa_response("Diesen Befehl kenne ich nicht.")

    elif request_type == "SessionEndedRequest":
        return Response(status_code=200)

    return build_alexa_response("Ich habe die Anfrage nicht verstanden.")


def register(api):
    api.register_router(router, tags=["alexa"])
    logger.info("Alexa Plugin geladen — Endpunkt: POST /api/alexa")
