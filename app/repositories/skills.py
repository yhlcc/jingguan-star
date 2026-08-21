from __future__ import annotations

import sqlite3
from typing import Any

from app.agent.playbooks import DEFAULT_SKILLS
from app.core.errors import BusinessError
from app.repositories.common import dumps, loads


def seed_default_skills(conn: sqlite3.Connection, seed_when_empty: bool = False) -> None:
    created = ensure_skill_table(conn)
    if not created and not seed_when_empty:
        return
    exists = conn.execute("SELECT 1 FROM agent_skill LIMIT 1").fetchone()
    if exists:
        _upgrade_default_skills(conn)
        return
    for skill in DEFAULT_SKILLS:
        save_skill(conn, skill.code, _default_skill_payload(skill), create=True)


def _upgrade_default_skills(conn: sqlite3.Connection) -> None:
    for skill in DEFAULT_SKILLS:
        row = conn.execute("SELECT steps_json,status FROM agent_skill WHERE skill_code=?", (skill.code,)).fetchone()
        if not row:
            save_skill(conn, skill.code, _default_skill_payload(skill), create=True)
            continue
        steps = loads(row["steps_json"], [])
        expected_step_ids = [step.step_id for step in skill.steps]
        current_step_ids = [item.get("stepId") for item in steps] if isinstance(steps, list) else []
        if current_step_ids == expected_step_ids:
            continue
        payload = _default_skill_payload(skill)
        payload["status"] = row["status"] or "启用"
        save_skill(conn, skill.code, payload, create=False)


def _default_skill_payload(skill) -> dict[str, Any]:
    return {
        "skillCode": skill.code,
        "skillName": skill.name,
        "description": skill.description,
        "triggerKeywords": list(skill.trigger_keywords),
        "steps": [
            {
                "stepId": step.step_id,
                "action": step.action,
                "interfaceCode": step.interface_code,
                "params": step.params,
                "paramSources": step.param_sources,
                "transform": step.transform,
                "dependsOn": list(step.depends_on),
                "purpose": step.purpose,
            }
            for step in skill.steps
        ],
        "derivedMetrics": list(skill.derived_metrics),
        "answerSections": list(skill.answer_sections),
        "status": "启用",
    }


def list_skills(conn: sqlite3.Connection, keyword: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    seed_default_skills(conn)
    where: list[str] = []
    values: list[Any] = []
    if keyword:
        where.append("(skill_code LIKE ? OR skill_name LIKE ? OR description LIKE ?)")
        values.extend([f"%{keyword}%"] * 3)
    if status:
        where.append("status=?")
        values.append(status)
    condition = f"WHERE {' AND '.join(where)}" if where else ""
    rows = conn.execute(f"SELECT * FROM agent_skill {condition} ORDER BY status, id", values).fetchall()
    return [_item(row, detail=False) for row in rows]


def enabled_skill_records(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    seed_default_skills(conn)
    rows = conn.execute("SELECT * FROM agent_skill WHERE status='启用' ORDER BY id").fetchall()
    return [_item(row, detail=True) for row in rows]


def enabled_skill_summaries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Lightweight catalog used for matching: no steps/derived metrics, avoids pulling full skill bodies."""
    seed_default_skills(conn)
    rows = conn.execute(
        "SELECT skill_code, skill_name, description, trigger_keywords FROM agent_skill WHERE status='启用' ORDER BY id"
    ).fetchall()
    return [
        {
            "code": row["skill_code"],
            "name": row["skill_name"],
            "description": row["description"] or "",
            "triggerKeywords": loads(row["trigger_keywords"], []),
        }
        for row in rows
    ]


def get_skill(conn: sqlite3.Connection, code: str) -> dict[str, Any]:
    seed_default_skills(conn)
    row = conn.execute("SELECT * FROM agent_skill WHERE skill_code=?", (code,)).fetchone()
    if not row:
        raise BusinessError("NOT_FOUND", "Skill 不存在", 404)
    return _item(row, detail=True)


def save_skill(conn: sqlite3.Connection, code: str, payload: dict[str, Any], create: bool = False) -> dict[str, Any]:
    ensure_skill_table(conn)
    code = code.strip()
    if not code:
        raise BusinessError("VALIDATION_ERROR", "skillCode 必填")
    if create and conn.execute("SELECT 1 FROM agent_skill WHERE skill_code=?", (code,)).fetchone():
        raise BusinessError("SKILL_EXISTS", "Skill 编码已存在，请更换后重试", 409)
    skill_name = str(payload.get("skillName") or payload.get("name") or code).strip()
    if not skill_name:
        raise BusinessError("VALIDATION_ERROR", "skillName 必填")
    status = str(payload.get("status") or "启用")
    if status not in ("启用", "停用"):
        raise BusinessError("VALIDATION_ERROR", "status 只能为启用或停用")
    trigger_keywords = _string_list(payload.get("triggerKeywords"))
    derived_metrics = _string_list(payload.get("derivedMetrics"))
    answer_sections = _string_list(payload.get("answerSections"))
    steps = _validate_steps(payload.get("steps"))
    values = (
        skill_name,
        str(payload.get("description") or ""),
        dumps(trigger_keywords),
        dumps(steps),
        dumps(derived_metrics),
        dumps(answer_sections),
        status,
    )
    if create:
        conn.execute("""INSERT INTO agent_skill(skill_code,skill_name,description,trigger_keywords,steps_json,derived_metrics_json,answer_sections_json,status)
                        VALUES(?,?,?,?,?,?,?,?)""", (code, *values))
    else:
        if not conn.execute("SELECT 1 FROM agent_skill WHERE skill_code=?", (code,)).fetchone():
            raise BusinessError("NOT_FOUND", "Skill 不存在", 404)
        conn.execute("""UPDATE agent_skill SET skill_name=?,description=?,trigger_keywords=?,steps_json=?,derived_metrics_json=?,answer_sections_json=?,status=?,updated_at=CURRENT_TIMESTAMP
                        WHERE skill_code=?""", (*values, code))
    return get_skill(conn, code)


def import_skills(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    seed_default_skills(conn)
    raw_items = payload.get("skills", payload)
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        raise BusinessError("VALIDATION_ERROR", "导入内容必须是 Skill JSON 或 Skill 数组")
    imported: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise BusinessError("VALIDATION_ERROR", "Skill 内容必须是对象")
        code = str(item.get("skillCode") or item.get("code") or "").strip()
        if not code:
            raise BusinessError("VALIDATION_ERROR", "导入 Skill 缺少 skillCode")
        exists = conn.execute("SELECT 1 FROM agent_skill WHERE skill_code=?", (code,)).fetchone()
        imported.append(save_skill(conn, code, _normalize_import_item(item, code), create=not bool(exists)))
    return {"items": imported, "count": len(imported)}


def set_skill_status(conn: sqlite3.Connection, code: str, status: str) -> dict[str, Any]:
    seed_default_skills(conn)
    if status not in ("启用", "停用"):
        raise BusinessError("VALIDATION_ERROR", "status 只能为启用或停用")
    if conn.execute("UPDATE agent_skill SET status=?,updated_at=CURRENT_TIMESTAMP WHERE skill_code=?", (status, code)).rowcount == 0:
        raise BusinessError("NOT_FOUND", "Skill 不存在", 404)
    return get_skill(conn, code)


def delete_skill(conn: sqlite3.Connection, code: str) -> dict[str, Any]:
    seed_default_skills(conn)
    if conn.execute("DELETE FROM agent_skill WHERE skill_code=?", (code,)).rowcount == 0:
        raise BusinessError("NOT_FOUND", "Skill 不存在", 404)
    return {"deleted": True, "skillCode": code}


def _item(row: sqlite3.Row, detail: bool) -> dict[str, Any]:
    steps = loads(row["steps_json"], [])
    item = {
        "id": row["id"],
        "skillCode": row["skill_code"],
        "skillName": row["skill_name"],
        "description": row["description"] or "",
        "triggerKeywords": loads(row["trigger_keywords"], []),
        "stepCount": len(steps) if isinstance(steps, list) else 0,
        "status": row["status"],
        "updatedAt": row["updated_at"],
    }
    if detail:
        item.update({
            "steps": steps if isinstance(steps, list) else [],
            "derivedMetrics": loads(row["derived_metrics_json"], []),
            "answerSections": loads(row["answer_sections_json"], []),
        })
    return item


def ensure_skill_table(conn: sqlite3.Connection) -> bool:
    existed = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_skill'").fetchone()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS agent_skill (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             skill_code TEXT NOT NULL UNIQUE,
             skill_name TEXT NOT NULL,
             description TEXT,
             trigger_keywords TEXT,
             steps_json TEXT NOT NULL,
             derived_metrics_json TEXT,
             answer_sections_json TEXT,
             status TEXT NOT NULL DEFAULT '启用',
             created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
             updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_skill_status ON agent_skill (status)")
    return not bool(existed)


def _normalize_import_item(item: dict[str, Any], code: str) -> dict[str, Any]:
    return {
        "skillCode": code,
        "skillName": item.get("skillName") or item.get("name") or code,
        "description": item.get("description") or "",
        "triggerKeywords": item.get("triggerKeywords") or item.get("trigger_keywords") or [],
        "steps": item.get("steps") or [],
        "derivedMetrics": item.get("derivedMetrics") or item.get("derived_metrics") or [],
        "answerSections": item.get("answerSections") or item.get("answer_sections") or [],
        "status": item.get("status") or "启用",
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_steps(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise BusinessError("VALIDATION_ERROR", "Skill 至少需要一个编排步骤")
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise BusinessError("VALIDATION_ERROR", f"第 {index} 个步骤必须是对象")
        action = str(item.get("action") or ("interface" if item.get("interfaceCode") else "derive")).strip()
        if action not in {"interface", "derive", "transform"}:
            raise BusinessError("VALIDATION_ERROR", f"第 {index} 个步骤 action 只能为 interface/derive/transform")
        interface_code = str(item.get("interfaceCode") or "").strip()
        if action == "interface" and not interface_code:
            raise BusinessError("VALIDATION_ERROR", f"第 {index} 个接口步骤缺少 interfaceCode")
        transform = item.get("transform") if isinstance(item.get("transform"), dict) else {}
        if action in {"derive", "transform"} and not transform:
            raise BusinessError("VALIDATION_ERROR", f"第 {index} 个派生步骤缺少 transform")
        step_id = str(item.get("stepId") or item.get("id") or interface_code or f"step{index}").strip()
        if not step_id:
            raise BusinessError("VALIDATION_ERROR", f"第 {index} 个步骤缺少 stepId")
        if step_id in seen:
            raise BusinessError("VALIDATION_ERROR", f"步骤 stepId 重复：{step_id}")
        seen.add(step_id)
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        param_sources = item.get("paramSources") or item.get("param_sources")
        if param_sources is None:
            param_sources = {}
        if not isinstance(param_sources, dict):
            raise BusinessError("VALIDATION_ERROR", f"第 {index} 个步骤 paramSources 必须是对象")
        depends_on = item.get("dependsOn") if isinstance(item.get("dependsOn"), list) else []
        steps.append({
            "stepId": step_id,
            "action": action,
            "interfaceCode": interface_code or None,
            "params": params,
            "paramSources": param_sources,
            "transform": transform,
            "dependsOn": [str(value).strip() for value in depends_on if str(value).strip()],
            "purpose": str(item.get("purpose") or ""),
        })
    return steps
