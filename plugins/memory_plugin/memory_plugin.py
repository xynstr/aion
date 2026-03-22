import json
import re
from datetime import datetime, UTC
from pathlib import Path

# BOT_DIR ist das Verzeichnis, in dem aion.py liegt.
# __file__ = .../AION/plugins/memory_plugin/memory_plugin.py
# .parent = memory_plugin/, .parent.parent = plugins/, .parent.parent.parent = AION/
BOT_DIR = Path(__file__).parent.parent.parent

HISTORY_FILE  = BOT_DIR / "conversation_history.jsonl"
HISTORY_MAX   = 1000  # Maximale Einträge — älteste werden entfernt


def _ts() -> str:
    return datetime.now(UTC).isoformat()


def append_to_history(role: str, content: str, channel: str = "default") -> dict:
    """Fügt einen neuen Eintrag zur Konversationshistorie hinzu (max HISTORY_MAX Einträge)."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {"role": role, "content": content, "ts": _ts(), "channel": channel}
    try:
        # Bestehende Einträge lesen und neuen anhängen
        lines = []
        if HISTORY_FILE.exists():
            lines = [l for l in HISTORY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
        lines.append(json.dumps(entry, ensure_ascii=False))
        # Auf HISTORY_MAX kürzen (älteste zuerst entfernen)
        if len(lines) > HISTORY_MAX:
            lines = lines[-HISTORY_MAX:]
        HISTORY_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_last_entries(num_entries: int = 50, channel_filter: str = "") -> dict:
    """
    Liest die letzten N Einträge aus der Konversationshistorie.
    channel_filter: wenn gesetzt, nur Einträge dieses Kanals zurückgeben.
      - "telegram" matcht alle telegram_* Kanäle
      - "web" matcht alle web* Kanäle
      - exakter Wert wie "telegram_123456" für einen bestimmten Chat
    Gibt sie im OpenAI-Format {role, content} zurück, ohne 'ts'.
    """
    if not HISTORY_FILE.exists():
        return {"ok": True, "entries": [], "note": "Noch keine Konversationshistorie gespeichert."}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

        # Channel-Filter anwenden (auf allen Einträgen, nicht nur den letzten N)
        if channel_filter:
            filtered = []
            for line in lines:
                try:
                    obj = json.loads(line)
                    ch = obj.get("channel", "default")
                    if ch == channel_filter or ch.startswith(channel_filter + "_"):
                        filtered.append(line)
                except Exception:
                    pass
            lines = filtered

        last_lines = lines[-num_entries:]
        entries = []
        for line in last_lines:
            try:
                obj = json.loads(line)
                entries.append({"role": obj["role"], "content": obj.get("content", "")})
            except Exception:
                pass
        return {"ok": True, "entries": entries}
    except Exception as e:
        return {"ok": False, "error": str(e), "entries": []}


def read_web_history(num_entries: int = 20) -> dict:
    """Liest die letzten N Einträge aus der Web-UI-History (channel=web*)."""
    return read_last_entries(num_entries=num_entries, channel_filter="web")


def search_context(query: str, max_results: int = 10) -> dict:
    """
    Durchsucht die gesamte Konversationshistorie semantisch nach relevanten Einträgen.
    Nutzt Keyword-Matching + Zeitgewichtung (neuere Einträge bevorzugt).
    """
    if not HISTORY_FILE.exists():
        return {"ok": True, "results": [], "note": "Keine History vorhanden."}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

        keywords = {w.lower() for w in re.split(r'\W+', query) if len(w) > 2}
        scored = []
        total = len(lines)
        for idx, line in enumerate(lines):
            try:
                obj = json.loads(line)
                text = obj.get("content", "").lower()
                # Keyword-Score
                kw_score = sum(1 for kw in keywords if kw in text)
                if kw_score == 0:
                    continue
                # Zeitgewichtung: neuere Einträge bekommen bis zu +2 Punkte
                time_score = (idx / max(total, 1)) * 2
                total_score = kw_score + time_score
                scored.append((total_score, obj))
            except Exception:
                pass

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _, obj in scored[:max_results]:
            results.append({
                "role": obj.get("role", "?"),
                "content": obj.get("content", "")[:400],
                "ts": obj.get("ts", "")[:10],
            })
        return {"ok": True, "results": results, "query": query, "total_searched": total}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def clear_history() -> dict:
    """Löscht die gesamte Konversationshistorie (irreversibel)."""
    try:
        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()
        return {"ok": True, "message": "Konversationshistorie gelöscht."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def register(api):
    api.register_tool(
        name="memory_append_history",
        description=(
            "Fügt einen Eintrag (Nutzer oder AION) mit Zeitstempel zur persistenten "
            "Konversationshistorie hinzu. Immer aufrufen nach jeder Antwort."
        ),
        func=append_to_history,
        input_schema={
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": "Rolle: 'user' oder 'assistant'"
                },
                "content": {
                    "type": "string",
                    "description": "Inhalt der Nachricht"
                },
                "channel": {
                    "type": "string",
                    "description": "Kanal: 'web', 'telegram_CHATID', 'heartbeat', etc."
                }
            },
            "required": ["role", "content"]
        }
    )

    api.register_tool(
        name="memory_read_history",
        description=(
            "Liest die letzten N Nachrichten aus der persistenten Konversationshistorie. "
            "Wird beim Start aufgerufen, um den Kontext wiederherzustellen."
        ),
        func=read_last_entries,
        input_schema={
            "type": "object",
            "properties": {
                "num_entries": {
                    "type": "integer",
                    "description": "Anzahl der letzten Einträge (Standard: 50)"
                },
                "channel_filter": {
                    "type": "string",
                    "description": "Kanal-Filter: z.B. 'telegram_123456', 'telegram', 'web'"
                }
            },
            "required": []
        }
    )

    api.register_tool(
        name="memory_read_web_history",
        description=(
            "Liest die letzten N Nachrichten aus der Web-UI-History. "
            "Nutze dieses Tool wenn der Nutzer fragt was im Web-Chat besprochen wurde, "
            "oder wenn er von Web auf Telegram wechselt und den Kontext mitbringen möchte."
        ),
        func=read_web_history,
        input_schema={
            "type": "object",
            "properties": {
                "num_entries": {
                    "type": "integer",
                    "description": "Anzahl der letzten Web-Einträge (Standard: 20)"
                }
            },
            "required": []
        }
    )

    api.register_tool(
        name="memory_search_context",
        description=(
            "Durchsucht die gesamte Konversationshistorie nach relevanten Einträgen "
            "zu einem Thema/einer Frage. Nutzt Keyword + Zeitgewichtung. "
            "Nutze dies wenn der Nutzer nach etwas fragt, das früher besprochen wurde."
        ),
        func=search_context,
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Suchanfrage oder Thema, nach dem gesucht werden soll"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximale Anzahl von Treffern (Standard: 10)"
                }
            },
            "required": ["query"]
        }
    )

    api.register_tool(
        name="memory_clear_history",
        description="Löscht die gesamte persistente Konversationshistorie. Nur auf explizite Nutzeranfrage!",
        func=clear_history,
        input_schema={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
