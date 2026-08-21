from __future__ import annotations

import sqlite3
import threading
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import settings


_lock = threading.Lock()
_checkpointer: SqliteSaver | MemorySaver | None = None


def get_checkpointer() -> SqliteSaver | MemorySaver:
    """Return the process-wide checkpointer (SqliteSaver by default, MemorySaver optional)."""
    global _checkpointer
    if _checkpointer is None:
        with _lock:
            if _checkpointer is None:
                if settings.checkpointer == "memory":
                    _checkpointer = MemorySaver()
                else:
                    settings.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                    conn = sqlite3.connect(settings.checkpoint_path, timeout=30, check_same_thread=False)
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA busy_timeout=5000")
                    _checkpointer = SqliteSaver(conn)
    return _checkpointer


def thread_id(session_id: int, run_id: str) -> str:
    return f"session-{session_id}:{run_id}"


def thread_config(session_id: int, run_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id(session_id, run_id)}}


def delete_session_checkpoints(session_id: int) -> None:
    """Remove every checkpoint thread belonging to a session (called when session is deleted)."""
    if settings.checkpointer == "memory":
        return
    try:
        conn = sqlite3.connect(settings.checkpoint_path, timeout=10)
        try:
            conn.execute(
                "DELETE FROM checkpoints WHERE thread_id LIKE ?", (f"session-{session_id}:%",)
            )
            conn.execute(
                "DELETE FROM writes WHERE thread_id LIKE ?", (f"session-{session_id}:%",)
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass


def list_run_checkpoints(session_id: int, run_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """List checkpoint snapshots of one run for replay/debug."""
    checkpointer = get_checkpointer()
    snapshots: list[dict[str, Any]] = []
    try:
        for item in checkpointer.list(thread_config(session_id, run_id), limit=limit):
            checkpoint = item.checkpoint if isinstance(item.checkpoint, dict) else {}
            values = checkpoint.get("channel_values") or {}
            snapshots.append({
                "checkpointId": (item.config or {}).get("configurable", {}).get("checkpoint_id"),
                "step": (item.metadata or {}).get("step"),
                "source": (item.metadata or {}).get("source"),
                "timestamp": (item.metadata or {}).get("ts"),
                "state": _state_summary(values),
            })
    except Exception:
        return []
    return snapshots


def _state_summary(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": values.get("question"),
        "intent": values.get("intent"),
        "matchedSkill": (values.get("matched_skill") or {}).get("code"),
        "planCalls": len((values.get("plan") or {}).get("calls", [])),
        "approvedCalls": len(values.get("approved_calls", []) or []),
        "executedInterfaces": [item.get("interfaceCode") for item in values.get("execution_results", []) or []],
        "validatedRowCount": sum(len(item.get("rows", []) or []) for item in values.get("validated_results", []) or []),
        "finalAnswer": (values.get("final_answer") or "")[:120],
        "errorCount": len(values.get("execution_errors", []) or []),
    }
