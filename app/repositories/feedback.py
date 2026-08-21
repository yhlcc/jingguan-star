from __future__ import annotations

import sqlite3
from typing import Any

from app.core.errors import BusinessError


def _item(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "sessionId": row["session_id"], "messageId": row["message_id"], "question": row["question"],
            "answerSnippet": row["answer_snippet"], "reason": row["reason"], "submitterName": row["submitter_name"],
            "status": row["status"], "handlerName": row["handler_name"], "handlerRemark": row["handler_remark"],
            "createdAt": row["created_at"], "handledAt": row["handled_at"]}


def list_feedback(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [_item(x) for x in conn.execute("SELECT * FROM qa_feedback ORDER BY created_at DESC LIMIT 100").fetchall()]


def get_feedback(conn: sqlite3.Connection, feedback_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM qa_feedback WHERE id=?", (feedback_id,)).fetchone()
    if not row: raise BusinessError("NOT_FOUND", "反馈不存在", 404)
    return _item(row)


def create_feedback(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    reason = str(payload.get("reason", "")).strip()
    if not reason:
        raise BusinessError("VALIDATION_ERROR", "请填写反馈原因")
    cursor = conn.execute("""INSERT INTO qa_feedback(session_id,message_id,question,answer_snippet,reason,submitter_name,status)
                            VALUES(?,?,?,?,?,?,'待处理')""", (payload.get("sessionId"), payload.get("messageId"), payload.get("question", "")[:500], payload.get("answerSnippet", "")[:1000], reason[:1000], payload.get("submitterName", "匿名用户")))
    return get_feedback(conn, int(cursor.lastrowid))


def update_feedback(conn: sqlite3.Connection, feedback_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("status", "已处理")
    if status not in ("待处理", "处理中", "已处理", "已关闭"): raise BusinessError("VALIDATION_ERROR", "反馈状态不合法")
    handled = "CURRENT_TIMESTAMP" if status in ("已处理", "已关闭") else "NULL"
    if conn.execute(f"UPDATE qa_feedback SET status=?,handler_name=?,handler_remark=?,handled_at={handled} WHERE id=?", (status, payload.get("handlerName", "经营管理部"), payload.get("handlerRemark", ""), feedback_id)).rowcount == 0:
        raise BusinessError("NOT_FOUND", "反馈不存在", 404)
    return get_feedback(conn, feedback_id)
