"""
AION Plugin: Multi-Agent Routing
==================================
Ermöglicht AION, Unteraufgaben an isolierte Sub-Agenten zu delegieren.
Jeder Sub-Agent ist eine eigene AionSession mit separater Konversationshistorie.

Tools:
    delegate_to_agent   — Neuen Sub-Agenten spawnen oder bestehenden nutzen
    sessions_list       — Alle aktiven Sub-Agenten anzeigen
    sessions_send       — Follow-up an bestehenden Sub-Agenten
    sessions_history    — Konversationsverlauf eines Sub-Agenten
"""

import uuid

# Registry aller aktiven Sub-Agenten: agent_id -> AionSession
_sub_sessions: dict[str, object] = {}


def _make_agent_id() -> str:
    return f"subagent_{str(uuid.uuid4())[:8]}"


def _get_current_channel() -> str:
    try:
        import aion as _aion
        return _aion._active_channel.get("default")
    except Exception:
        return "default"


# ── Tools ──────────────────────────────────────────────────────────────────────

async def delegate_to_agent(
    task:    str = "",
    agent_id: str = "",
    context: str = "",
    reuse:   bool = False,
    **_,
) -> dict:
    """Delegiert eine Aufgabe an einen Sub-Agenten und wartet auf das Ergebnis."""
    if not task:
        return {"error": "Kein 'task' angegeben."}

    # Rekursionsschutz: Sub-Agenten können nicht weiter delegieren
    current = _get_current_channel()
    if "subagent_" in current:
        return {"error": "Rekursion verhindert: Sub-Agenten können nicht weiter delegieren."}

    from aion import AionSession

    # Session bestimmen
    if reuse and agent_id and agent_id in _sub_sessions:
        sess = _sub_sessions[agent_id]
    else:
        if not agent_id:
            agent_id = _make_agent_id()
        sess = AionSession(channel=agent_id)
        _sub_sessions[agent_id] = sess

    # Aufgabe ggf. mit Kontext anreichern
    prompt = task
    if context:
        prompt = f"[Kontext vom übergeordneten Agenten]:\n{context}\n\n[Aufgabe]:\n{task}"

    try:
        result = await sess.turn(prompt)
        return {
            "ok":       True,
            "agent_id": agent_id,
            "result":   result,
        }
    except Exception as e:
        return {"ok": False, "agent_id": agent_id, "error": str(e)}


def sessions_list(**_) -> dict:
    """Zeigt alle aktiven Sub-Agenten mit ihrer Session-ID und Nachrichtenzahl."""
    agents = {
        aid: {
            "channel":       getattr(sess, "channel", aid),
            "nachrichten":   len(getattr(sess, "messages", [])),
        }
        for aid, sess in _sub_sessions.items()
    }
    return {"ok": True, "sub_agenten": agents, "anzahl": len(agents)}


async def sessions_send(
    agent_id: str = "",
    message:  str = "",
    **_,
) -> dict:
    """Sendet eine Folgenachricht an einen bestehenden Sub-Agenten."""
    if not agent_id:
        return {"error": "Kein 'agent_id' angegeben."}
    if agent_id not in _sub_sessions:
        return {
            "error":     f"Kein Sub-Agent mit ID '{agent_id}' gefunden.",
            "verfügbar": list(_sub_sessions.keys()),
        }
    if not message:
        return {"error": "Keine 'message' angegeben."}

    sess = _sub_sessions[agent_id]
    try:
        result = await sess.turn(message)
        return {"ok": True, "agent_id": agent_id, "result": result}
    except Exception as e:
        return {"ok": False, "agent_id": agent_id, "error": str(e)}


def sessions_history(agent_id: str = "", **_) -> dict:
    """Gibt die letzten 20 Nachrichten eines Sub-Agenten zurück."""
    if not agent_id:
        return {"error": "Kein 'agent_id' angegeben."}
    if agent_id not in _sub_sessions:
        return {
            "error":     f"Kein Sub-Agent mit ID '{agent_id}' gefunden.",
            "verfügbar": list(_sub_sessions.keys()),
        }

    sess     = _sub_sessions[agent_id]
    messages = getattr(sess, "messages", [])
    last_20  = [
        {
            "rolle":   m.get("role", "?"),
            "inhalt":  str(m.get("content", ""))[:500],
        }
        for m in messages[-20:]
        if m.get("role") in ("user", "assistant")
    ]
    return {
        "ok":       True,
        "agent_id": agent_id,
        "nachrichten": last_20,
        "gesamt":   len(messages),
    }


# ── Register ───────────────────────────────────────────────────────────────────

def register(api):
    api.register_tool(
        name="delegate_to_agent",
        description=(
            "Delegiert eine Unteraufgabe an einen isolierten Sub-Agenten und gibt dessen Antwort zurück. "
            "Nützlich für parallele oder spezialisierte Aufgaben. "
            "Mit 'agent_id' und 'reuse=true' kann eine bestehende Sub-Session weitergeführt werden."
        ),
        func=delegate_to_agent,
        input_schema={
            "type": "object",
            "properties": {
                "task":     {"type": "string",  "description": "Die zu delegierende Aufgabe."},
                "agent_id": {"type": "string",  "description": "Optionale ID — für Wiederverwenden einer Session."},
                "context":  {"type": "string",  "description": "Optionaler Kontext für den Sub-Agenten."},
                "reuse":    {"type": "boolean", "description": "True = bestehende Session mit dieser ID wiederverwenden."},
            },
            "required": ["task"],
        },
    )
    api.register_tool(
        name="sessions_list",
        description="Listet alle aktiven Sub-Agenten-Sessions mit ID und Nachrichtenzahl auf.",
        func=sessions_list,
        input_schema={"type": "object", "properties": {}},
    )
    api.register_tool(
        name="sessions_send",
        description="Sendet eine Folgenachricht an eine bestehende Sub-Agenten-Session.",
        func=sessions_send,
        input_schema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Die ID des Sub-Agenten."},
                "message":  {"type": "string", "description": "Die zu sendende Nachricht."},
            },
            "required": ["agent_id", "message"],
        },
    )
    api.register_tool(
        name="sessions_history",
        description="Gibt den Konversationsverlauf (letzte 20 Nachrichten) eines Sub-Agenten zurück.",
        func=sessions_history,
        input_schema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Die ID des Sub-Agenten."},
            },
            "required": ["agent_id"],
        },
    )

    print("[multi_agent] 4 Multi-Agent-Tools registriert.")
