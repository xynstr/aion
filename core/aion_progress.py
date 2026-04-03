"""
aion_progress — Lightweight progress reporting for long-running AION tools.

Usage in any tool/plugin:
    from core.aion_progress import report
    report(42, "Absatz 3/7")   # percent 0–100, optional label

The session layer polls this state and emits SSE progress events to the frontend.
"""
import contextvars
import threading

# Per-async-task / per-thread active call ID (set by aion_session before dispatch)
_current_call_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "aion_progress_call_id", default=""
)

_store: dict[str, dict] = {}
_lock = threading.Lock()


def set_active(call_id: str) -> None:
    """Called by aion_session right before a tool is dispatched."""
    _current_call_id.set(call_id)


def report(percent: int, label: str = "") -> None:
    """Called by tools to report progress.  percent: 0–100."""
    cid = _current_call_id.get("")
    if not cid:
        return
    percent = max(0, min(100, int(percent)))
    with _lock:
        _store[cid] = {"percent": percent, "label": label}


def get(call_id: str) -> dict | None:
    """Returns latest progress dict for call_id, or None."""
    return _store.get(call_id)


def clear(call_id: str) -> None:
    """Called by aion_session after the tool finishes."""
    with _lock:
        _store.pop(call_id, None)
