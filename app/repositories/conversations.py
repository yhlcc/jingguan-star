from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.core.errors import BusinessError
from app.repositories.common import dumps, loads


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_session(conn: sqlite3.Connection, title: str = "新的问数会话") -> dict[str, Any]:
    cursor = conn.execute("INSERT INTO qa_session(title,client_name) VALUES(?,?)", (title[:100], "web"))
    return {"id": cursor.lastrowid, "title": title[:100], "messageCount": 0, "pinned": False, "createdAt": now_iso(), "updatedAt": now_iso()}


def list_sessions(conn: sqlite3.Connection, keyword: str | None = None) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM qa_session WHERE title LIKE ? ORDER BY pinned DESC,updated_at DESC LIMIT 50", (f"%{keyword or ''}%",)).fetchall()
    return [{"id": x["id"], "title": x["title"], "messageCount": x["message_count"], "pinned": bool(x["pinned"]), "updatedAt": x["updated_at"]} for x in rows]


def get_messages(conn: sqlite3.Connection, session_id: int) -> dict[str, Any]:
    session = conn.execute("SELECT * FROM qa_session WHERE id=?", (session_id,)).fetchone()
    if not session:
        raise BusinessError("NOT_FOUND", "会话不存在", 404)
    rows = conn.execute("SELECT * FROM qa_message WHERE session_id=? ORDER BY created_at,id", (session_id,)).fetchall()
    return {"session": {"id": session["id"], "title": session["title"], "messageCount": session["message_count"], "pinned": bool(session["pinned"]), "updatedAt": session["updated_at"]},
            "messages": [{"id": x["id"], "role": x["role"], "content": x["content"], "interfaceCalls": loads(x["interface_calls"], []), "answerPayload": loads(x["chart_config"]), "createdAt": x["created_at"]} for x in rows]}


def history(conn: sqlite3.Connection, session_id: int, limit: int = 12) -> list[dict[str, str]]:
    rows = conn.execute(
        """SELECT role,content FROM qa_message WHERE session_id=?
           ORDER BY created_at DESC,id DESC LIMIT ?""",
        (session_id, max(1, min(limit, 50))),
    ).fetchall()
    return [{"role": x["role"], "content": x["content"]} for x in reversed(rows)]


def add_message(conn: sqlite3.Connection, session_id: int, role: str, content: str, calls: Any = None, answer: Any = None) -> int:
    cursor = conn.execute("INSERT INTO qa_message(session_id,role,content,interface_calls,chart_config) VALUES(?,?,?,?,?)", (session_id, role, content, dumps(calls or []), dumps(answer) if answer else None))
    conn.execute("UPDATE qa_session SET message_count=message_count+1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (session_id,))
    if role == "user":
        _record_frequent(conn, content)
        if conn.execute("SELECT message_count FROM qa_session WHERE id=?", (session_id,)).fetchone()[0] <= 1:
            conn.execute("UPDATE qa_session SET title=? WHERE id=?", (content[:32], session_id))
    return int(cursor.lastrowid)


def delete_session(conn: sqlite3.Connection, session_id: int) -> dict[str, Any]:
    if conn.execute("DELETE FROM qa_session WHERE id=?", (session_id,)).rowcount == 0:
        raise BusinessError("NOT_FOUND", "会话不存在", 404)
    return {"deleted": True, "id": session_id}


def _record_frequent(conn: sqlite3.Connection, question: str) -> None:
    config = conn.execute(
        "SELECT frequent_enabled, frequent_threshold FROM app_config WHERE id=1"
    ).fetchone()
    if not config or not config["frequent_enabled"]:
        return
    threshold = max(1, min(int(config["frequent_threshold"] or 3), 20))
    normalized = " ".join(question.strip().lower().split())
    recent = conn.execute(
        "SELECT content FROM qa_message WHERE role='user' ORDER BY id DESC LIMIT ?", (threshold,)
    ).fetchall()
    if len(recent) == threshold and all(" ".join(x[0].strip().lower().split()) == normalized for x in recent):
        conn.execute("""INSERT INTO qa_frequent_question(question,normalized_question,hit_count) VALUES(?,?,?)
                        ON CONFLICT(normalized_question) DO UPDATE SET question=excluded.question,hit_count=hit_count+1,last_asked_at=CURRENT_TIMESTAMP""",
                     (question[:120], normalized, threshold))
