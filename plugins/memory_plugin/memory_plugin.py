import json
import re
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

# BOT_DIR ist das Directory, in dem aion.py liegt.
# __file__ = .../AION/plugins/memory_plugin/memory_plugin.py
# .parent = memory_plugin/, .parent.parent = plugins/, .parent.parent.parent = AION/
BOT_DIR = Path(__file__).parent.parent.parent

HISTORY_FILE  = BOT_DIR / "conversation_history.jsonl"
HISTORY_MAX   = 1000  # Maximale Einträge — älteste werden entfernt
_APPEND_COUNT = 0     # Zähler für gelegentliches Kürzen (alle 100 Appends)


def _ts() -> str:
    return datetime.now(UTC).isoformat()


def _trim_history() -> None:
    """Kürzt die History-Datei auf HISTORY_MAX Einträge. Nur gelegentlich aufrufen."""
    if not HISTORY_FILE.exists():
        return
    try:
        lines = [l for l in HISTORY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
        if len(lines) > HISTORY_MAX:
            lines = lines[-HISTORY_MAX:]
            HISTORY_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def append_to_history(role: str, content: str, channel: str = "default") -> dict:
    """Fügt einen neuen Eintrag zur Konversationshistorie hinzu.
    Nutzt echtes File-Append statt Read-Modify-Write — effizienter und race-sicherer.
    Kürzt alle 100 Einträge auf HISTORY_MAX."""
    global _APPEND_COUNT
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {"role": role, "content": content, "ts": _ts(), "channel": channel}
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _APPEND_COUNT += 1
        if _APPEND_COUNT % 100 == 0:
            _trim_history()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_last_entries(num_entries: int = 50, channel_filter: str = "") -> dict:
    """
    Liest die letzten N Einträge aus der Konversationshistorie.
    channel_filter: wenn gesetzt, nur Einträge dieses Channels zurückgeben.
      - "telegram" matcht alle telegram_* Channels
      - "web" matcht alle web* Channels
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
    """Reads die letzten N Einträge aus der Web-UI-History (channel=web*)."""
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
        description="Append a message (role + content) to the persistent conversation history.",
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
                    "description": "Channel: 'web', 'telegram_CHATID', 'heartbeat', etc."
                }
            },
            "required": ["role", "content"]
        }
    )

    api.register_tool(
        name="memory_read_history",
        description="Read the last N messages from the persistent conversation history.",
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
                    "description": "Channel-Filter: z.B. 'telegram_123456', 'telegram', 'web'"
                }
            },
            "required": []
        }
    )

    api.register_tool(
        name="memory_read_web_history",
        description="Read the last N messages from the Web UI history. Use when the user switches from web to another channel and needs context.",
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
        description="Search the full conversation history for relevant entries on a topic. Use when the user references something discussed earlier.",
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
        description="Löscht die gesamte persistente Konversationshistorie. Nur auf explizite Useranfrage!",
        func=clear_history,
        input_schema={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
