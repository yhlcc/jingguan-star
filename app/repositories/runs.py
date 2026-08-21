from __future__ import annotations

import sqlite3
from typing import Any

from app.core.errors import BusinessError


def ensure_run_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS agent_run (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             session_id INTEGER NOT NULL,
             run_id TEXT NOT NULL UNIQUE,
             thread_id TEXT NOT NULL UNIQUE,
             question TEXT,
             status TEXT NOT NULL DEFAULT 'running',
             error TEXT,
             created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
             updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_run_session ON agent_run (session_id)")


def create_run(conn: sqlite3.Connection, session_id: int, run_id: str, thread_id: str, question: str) -> dict[str, Any]:
    ensure_run_table(conn)
    conn.execute(
        "INSERT INTO agent_run(session_id,run_id,thread_id,question) VALUES(?,?,?,?)",
        (session_id, run_id, thread_id, question[:500]),
    )
    return {"runId": run_id, "threadId": thread_id, "sessionId": session_id, "status": "running"}


def update_run_status(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    error: str | None = None,
) -> None:
    ensure_run_table(conn)
    conn.execute(
        "UPDATE agent_run SET status=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE run_id=?",
        (status, (error or "")[:1000], run_id),
    )


def list_session_runs(conn: sqlite3.Connection, session_id: int, limit: int = 30) -> list[dict[str, Any]]:
    ensure_run_table(conn)
    rows = conn.execute(
        "SELECT * FROM agent_run WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, limit)
    ).fetchall()
    return [
        {
            "runId": row["run_id"],
            "threadId": row["thread_id"],
            "question": row["question"] or "",
            "status": row["status"],
            "error": row["error"] or "",
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def get_run(conn: sqlite3.Connection, session_id: int, run_id: str) -> dict[str, Any]:
    ensure_run_table(conn)
    row = conn.execute(
        "SELECT * FROM agent_run WHERE session_id=? AND run_id=?", (session_id, run_id)
    ).fetchone()
    if not row:
        raise BusinessError("NOT_FOUND", "运行记录不存在", 404)
    return {
        "runId": row["run_id"],
        "threadId": row["thread_id"],
        "question": row["question"] or "",
        "status": row["status"],
        "error": row["error"] or "",
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def delete_session_runs(conn: sqlite3.Connection, session_id: int) -> None:
    ensure_run_table(conn)
    conn.execute("DELETE FROM agent_run WHERE session_id=?", (session_id,))
