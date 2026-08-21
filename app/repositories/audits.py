from __future__ import annotations

import sqlite3
from typing import Any

from app.core.errors import BusinessError
from app.repositories.common import clamp_page_size, dumps, loads


def write_audit(conn: sqlite3.Connection, *, request_id: str, session_id: int | None, interface_code: str, params: dict[str, Any], row_count: int, duration_ms: int, status: str, error: str | None = None) -> None:
    conn.execute("""INSERT INTO ai_query_call_audit(request_id,session_id,client_name,interface_code,request_params,response_row_count,duration_ms,status,error_message)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (request_id, session_id, "agent", interface_code, dumps(params), row_count, duration_ms, status, error))


def _item(row: sqlite3.Row, parse: bool = False) -> dict[str, Any]:
    return {"id": row["id"], "requestId": row["request_id"], "sessionId": row["session_id"], "clientName": row["client_name"],
            "interfaceCode": row["interface_code"], "requestParams": loads(row["request_params"], {}) if parse else row["request_params"],
            "responseRowCount": row["response_row_count"], "durationMs": row["duration_ms"], "status": row["status"],
            "errorMessage": row["error_message"], "createdAt": row["created_at"]}


def list_audits(conn: sqlite3.Connection, page_size: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM ai_query_call_audit ORDER BY created_at DESC,id DESC LIMIT ?", (clamp_page_size(page_size),)).fetchall()
    return [_item(x) for x in rows]


def get_audit(conn: sqlite3.Connection, audit_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM ai_query_call_audit WHERE id=?", (audit_id,)).fetchone()
    if not row:
        raise BusinessError("NOT_FOUND", "审计记录不存在", 404)
    return _item(row, True)
