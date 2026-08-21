from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from app.core.errors import BusinessError
from app.repositories.common import dumps, loads
from app.services.interface_registry import EXECUTABLE_INTERFACE_CODES


APPROVAL_POLICY_NONE = "none"
APPROVAL_POLICY_MANUAL = "manual"
APPROVAL_POLICIES = {APPROVAL_POLICY_NONE, APPROVAL_POLICY_MANUAL}
DEFAULT_MANUAL_APPROVAL_CODES = {"ledger.commercial.detail", "ledger.ppl.detail"}


def ensure_interface_approval_policy(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(ai_query_interface)").fetchall()}
    if "approval_policy" in columns:
        return
    conn.execute("ALTER TABLE ai_query_interface ADD COLUMN approval_policy TEXT NOT NULL DEFAULT 'none'")
    if DEFAULT_MANUAL_APPROVAL_CODES:
        placeholders = ",".join("?" for _ in DEFAULT_MANUAL_APPROVAL_CODES)
        conn.execute(
            f"UPDATE ai_query_interface SET approval_policy=? WHERE interface_code IN ({placeholders})",
            (APPROVAL_POLICY_MANUAL, *DEFAULT_MANUAL_APPROVAL_CODES),
        )


def interface_requires_approval(conn: sqlite3.Connection, code: str) -> bool:
    detail = get_interface(conn, code)
    return detail["approvalPolicy"] == APPROVAL_POLICY_MANUAL


def list_interfaces(conn: sqlite3.Connection, keyword: str | None = None, status: str | None = None, group_name: str | None = None) -> list[dict[str, Any]]:
    ensure_interface_approval_policy(conn)
    where: list[str] = []
    values: list[Any] = []
    if keyword:
        where.append("(i.interface_code LIKE ? OR i.interface_name LIKE ? OR i.path LIKE ?)")
        values.extend([f"%{keyword}%"] * 3)
    if status:
        where.append("i.status=?")
        values.append(status)
    if group_name:
        where.append("i.group_name=?")
        values.append(group_name)
    condition = f"WHERE {' AND '.join(where)}" if where else ""
    rows = conn.execute(
        f"""SELECT i.*, COUNT(DISTINCT p.id) AS param_count,
                   GROUP_CONCAT(DISTINCT f.field_label) AS field_labels
            FROM ai_query_interface i
            LEFT JOIN ai_query_interface_param p ON p.interface_code=i.interface_code
            LEFT JOIN ai_query_interface_field f ON f.interface_code=i.interface_code
            {condition} GROUP BY i.id ORDER BY i.group_name, i.id""",
        values,
    ).fetchall()
    return [{
        "interfaceCode": row["interface_code"], "interfaceName": row["interface_name"],
        "groupName": row["group_name"], "method": row["method"], "path": row["path"],
        "ownerDept": row["owner_dept"], "paramCount": row["param_count"],
        "fields": (row["field_labels"] or "").replace(",", "、"), "status": row["status"],
        "approvalPolicy": row["approval_policy"],
        "executable": row["interface_code"] in EXECUTABLE_INTERFACE_CODES,
        "description": row["description"],
    } for row in rows]


def get_interface(conn: sqlite3.Connection, code: str) -> dict[str, Any]:
    ensure_interface_approval_policy(conn)
    row = conn.execute("SELECT * FROM ai_query_interface WHERE interface_code=?", (code,)).fetchone()
    if not row:
        raise BusinessError("NOT_FOUND", "接口不存在", 404)
    params = conn.execute("SELECT * FROM ai_query_interface_param WHERE interface_code=? ORDER BY sort_order,id", (code,)).fetchall()
    fields = conn.execute("SELECT * FROM ai_query_interface_field WHERE interface_code=? ORDER BY sort_order,id", (code,)).fetchall()
    return {
        "interfaceCode": row["interface_code"], "interfaceName": row["interface_name"], "groupName": row["group_name"],
        "method": row["method"], "path": row["path"], "ownerDept": row["owner_dept"], "description": row["description"],
        "securityPolicy": row["security_policy"], "cachePolicy": row["cache_policy"], "rateLimitPolicy": row["rate_limit_policy"],
        "status": row["status"], "approvalPolicy": row["approval_policy"], "executable": row["interface_code"] in EXECUTABLE_INTERFACE_CODES,
        "params": [{"name": x["param_name"], "type": x["param_type"], "required": bool(x["required"]),
                    "enumJson": loads(x["enum_json"]), "defaultValue": x["default_value"], "description": x["description"]} for x in params],
        "fields": [{"name": x["field_name"], "label": x["field_label"], "type": x["field_type"], "unit": x["unit"],
                    "sensitiveLevel": x["sensitive_level"], "description": x["description"]} for x in fields],
        "aiExample": {"requestId": str(uuid.uuid4()), "filters": {"year": 2026}, "dimensions": [], "metrics": []},
    }


def interface_specs(conn: sqlite3.Connection, only_enabled: bool = True) -> list[dict[str, Any]]:
    items = list_interfaces(conn, status="启用" if only_enabled else None)
    return [{"code": x["interfaceCode"], "name": x["interfaceName"], "description": x["description"], "executable": x["executable"],
             "approvalPolicy": x["approvalPolicy"],
             "params": get_interface(conn, x["interfaceCode"])["params"]} for x in items]


def allowed_params(conn: sqlite3.Connection, code: str) -> dict[str, dict[str, Any]]:
    detail = get_interface(conn, code)
    return {item["name"]: item for item in detail["params"]}


def allowed_fields(conn: sqlite3.Connection, code: str) -> list[dict[str, Any]]:
    detail = get_interface(conn, code)
    return [{"field": x["name"], "label": x["label"], "type": x["type"], "unit": x["unit"] or ""} for x in detail["fields"]]


def save_interface(conn: sqlite3.Connection, code: str, payload: dict[str, Any], create: bool = False) -> dict[str, Any]:
    ensure_interface_approval_policy(conn)
    if not code:
        raise BusinessError("VALIDATION_ERROR", "interfaceCode 必填")
    if create and conn.execute("SELECT 1 FROM ai_query_interface WHERE interface_code=?", (code,)).fetchone():
        raise BusinessError("INTERFACE_EXISTS", "接口编码已存在，请更换后重试", 409)
    status = payload.get("status") or "启用"
    if status not in ("启用", "停用"):
        raise BusinessError("VALIDATION_ERROR", "status 只能为启用或停用")
    approval_policy = str(payload.get("approvalPolicy") or payload.get("approval_policy") or APPROVAL_POLICY_NONE)
    if approval_policy not in APPROVAL_POLICIES:
        raise BusinessError("VALIDATION_ERROR", "approvalPolicy 只能为 none 或 manual")
    params_payload = _validate_param_specs(payload.get("params"))
    fields_payload = _validate_field_specs(payload.get("fields"))
    values = (payload.get("interfaceName") or code, payload.get("groupName") or "自定义接口", payload.get("method") or "POST",
              payload.get("path") or f"/api/ai-query/{code}", payload.get("ownerDept") or "经营管理部",
              payload.get("description") or "自定义受控问数接口", payload.get("securityPolicy") or "接口、参数和字段白名单。",
              payload.get("cachePolicy") or "无", payload.get("rateLimitPolicy") or "每分钟 60 次", status, approval_policy)
    if create:
        conn.execute("""INSERT INTO ai_query_interface(interface_code,interface_name,group_name,method,path,owner_dept,description,security_policy,cache_policy,rate_limit_policy,status,approval_policy)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (code, *values))
    else:
        if not conn.execute("SELECT 1 FROM ai_query_interface WHERE interface_code=?", (code,)).fetchone():
            raise BusinessError("NOT_FOUND", "接口不存在", 404)
        conn.execute("""UPDATE ai_query_interface SET interface_name=?,group_name=?,method=?,path=?,owner_dept=?,description=?,security_policy=?,cache_policy=?,rate_limit_policy=?,status=?,approval_policy=?,updated_at=CURRENT_TIMESTAMP
                        WHERE interface_code=?""", (*values, code))
    conn.execute("DELETE FROM ai_query_interface_param WHERE interface_code=?", (code,))
    for index, item in enumerate(params_payload, 1):
        conn.execute("""INSERT INTO ai_query_interface_param(interface_code,param_name,param_type,required,enum_json,description,sort_order)
                        VALUES(?,?,?,?,?,?,?)""", (code, item["name"], item.get("type", "string"), int(bool(item.get("required"))), dumps(item.get("enum") or item.get("enumJson")) if item.get("enum") or item.get("enumJson") else None, item.get("description", ""), index))
    conn.execute("DELETE FROM ai_query_interface_field WHERE interface_code=?", (code,))
    for index, item in enumerate(fields_payload, 1):
        conn.execute("""INSERT INTO ai_query_interface_field(interface_code,field_name,field_label,field_type,unit,sensitive_level,description,sort_order)
                        VALUES(?,?,?,?,?,?,?,?)""", (code, item["name"], item.get("label") or item["name"], item.get("type", "string"), item.get("unit", ""), item.get("sensitiveLevel", "internal"), item.get("description", ""), index))
    return get_interface(conn, code)


def set_interface_status(conn: sqlite3.Connection, code: str, status: str) -> dict[str, Any]:
    if status not in ("启用", "停用"):
        raise BusinessError("VALIDATION_ERROR", "status 只能为启用或停用")
    if conn.execute("UPDATE ai_query_interface SET status=?,updated_at=CURRENT_TIMESTAMP WHERE interface_code=?", (status, code)).rowcount == 0:
        raise BusinessError("NOT_FOUND", "接口不存在", 404)
    return get_interface(conn, code)


def _validate_param_specs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise BusinessError("VALIDATION_ERROR", "接口入参格式 params 必须是非空数组")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise BusinessError("VALIDATION_ERROR", f"第 {index} 个入参必须是对象")
        name = str(item.get("name") or "").strip()
        if not name:
            raise BusinessError("VALIDATION_ERROR", f"第 {index} 个入参缺少 name")
        if name in seen:
            raise BusinessError("VALIDATION_ERROR", f"入参 name 重复：{name}")
        seen.add(name)
        result.append({**item, "name": name, "type": str(item.get("type") or "string")})
    return result


def _validate_field_specs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise BusinessError("VALIDATION_ERROR", "接口出参格式 fields 必须是非空数组")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise BusinessError("VALIDATION_ERROR", f"第 {index} 个出参必须是对象")
        name = str(item.get("name") or "").strip()
        if not name:
            raise BusinessError("VALIDATION_ERROR", f"第 {index} 个出参缺少 name")
        if name in seen:
            raise BusinessError("VALIDATION_ERROR", f"出参 name 重复：{name}")
        seen.add(name)
        result.append({**item, "name": name, "type": str(item.get("type") or "string")})
    return result
