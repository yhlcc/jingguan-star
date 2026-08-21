from __future__ import annotations

import unittest
import uuid

from fastapi.testclient import TestClient

from app.core.database import connect
from app.core.errors import BusinessError
from app.main import app
from app.repositories.catalog import save_interface
from app.repositories.conversations import create_session
from app.repositories.feedback import create_feedback
from app.repositories.runs import create_run, list_session_runs
from app.repositories.settings import get_app_config, update_app_config
from app.services.query_gateway import QueryGateway


class ApiSmokeTests(unittest.TestCase):
    def test_core_read_endpoints(self) -> None:
        with TestClient(app) as client:
            for path in ("/api/health", "/api/dashboard?year=2026", "/api/query-interfaces?status=启用", "/api/app-config", "/api/llm-config"):
                response = client.get(path)
                self.assertEqual(response.status_code, 200, (path, response.text))

    def test_app_config_supports_greeting_and_frequent_threshold(self) -> None:
        conn = connect()
        try:
            current = get_app_config(conn)
            candidate = {
                **current,
                "greetingEnabled": False,
                "openingGreeting": "联动验证欢迎语",
                "openingQuestions": ["问题一", "问题二"],
                "frequentEnabled": True,
                "frequentThreshold": 5,
            }
            updated = update_app_config(conn, candidate)
            self.assertFalse(updated["greetingEnabled"])
            self.assertEqual(updated["openingGreeting"], "联动验证欢迎语")
            self.assertEqual(updated["openingQuestions"], ["问题一", "问题二"])
            self.assertEqual(updated["frequentThreshold"], 5)
        finally:
            conn.rollback()
            conn.close()

    def test_custom_interface_can_be_created_and_duplicate_code_is_rejected(self) -> None:
        conn = connect()
        code = f"custom.test.{uuid.uuid4().hex[:8]}"
        try:
            with self.assertRaises(BusinessError) as missing:
                save_interface(conn, f"{code}.missing", {
                    "interfaceCode": f"{code}.missing",
                    "interfaceName": "缺少格式的接口",
                    "status": "启用",
                }, create=True)
            self.assertEqual(missing.exception.code, "VALIDATION_ERROR")

            created = save_interface(conn, code, {
                "interfaceCode": code,
                "interfaceName": "自动化测试接口",
                "path": f"/api/ai-query/{code}",
                "params": [{"name": "year", "type": "int", "required": False, "description": "年份"}],
                "fields": [{"name": "value", "label": "数值", "type": "decimal", "unit": "万元"}],
                "status": "启用",
            }, create=True)
            self.assertEqual(created["interfaceCode"], code)
            self.assertEqual(created["interfaceName"], "自动化测试接口")
            self.assertEqual(created["approvalPolicy"], "none")
            self.assertFalse(created["executable"])
            with self.assertRaises(BusinessError) as caught:
                save_interface(conn, code, {"interfaceName": "重复接口"}, create=True)
            self.assertEqual(caught.exception.code, "INTERFACE_EXISTS")
        finally:
            conn.rollback()
            conn.close()

    def test_gateway_validates_types_enums_and_detail_filters(self) -> None:
        conn = connect()
        try:
            gateway = QueryGateway(conn)
            with self.assertRaises(BusinessError) as caught:
                gateway.approve("biz.dashboard.summary", {"year": "not-a-year"})
            self.assertEqual(caught.exception.code, "PARAM_TYPE_INVALID")

            with self.assertRaises(BusinessError) as caught:
                gateway.approve("ledger.pplRisk.summary", {"riskLevels": ["紧急"]})
            self.assertEqual(caught.exception.code, "PARAM_ENUM_INVALID")

            params = gateway.approve("ledger.commercial.detail", {"year": 2026, "productLines": ["GC"], "pageSize": 100})
            result = gateway.execute("ledger.commercial.detail", params)
            contract_nos = [row["contractNo"] for row in result["rows"]]
            self.assertTrue(contract_nos)
            placeholders = ",".join("?" for _ in contract_nos)
            db_rows = conn.execute(
                f"SELECT DISTINCT product_line_code FROM ledger_commercial_contract WHERE contract_no IN ({placeholders})",
                contract_nos,
            ).fetchall()
            self.assertEqual({row[0] for row in db_rows}, {"GC"})
        finally:
            conn.rollback()
            conn.close()

    def test_skill_management_create_import_toggle_and_delete(self) -> None:
        with TestClient(app) as client:
            code = f"custom.skill.{uuid.uuid4().hex[:8]}"
            payload = {
                "skillCode": code,
                "skillName": "测试 Skill",
                "description": "用于验证 Skill 管理闭环",
                "triggerKeywords": ["测试", "Skill"],
                "steps": [{"interfaceCode": "biz.dashboard.summary", "params": {"year": "$year"}, "purpose": "查询概览"}],
                "derivedMetrics": ["completionRate"],
                "answerSections": ["概览"],
                "status": "启用",
            }
            created = client.post("/api/agent-skills", json=payload)
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(created.json()["skillCode"], code)

            toggled = client.patch(f"/api/agent-skills/{code}/status", json={"status": "停用"})
            self.assertEqual(toggled.status_code, 200, toggled.text)
            self.assertEqual(toggled.json()["status"], "停用")

            imported_code = f"custom.skill.imported.{uuid.uuid4().hex[:8]}"
            imported = client.post("/api/agent-skills/import", json={**payload, "skillCode": imported_code, "skillName": "导入 Skill"})
            self.assertEqual(imported.status_code, 200, imported.text)
            self.assertEqual(imported.json()["count"], 1)

            deleted = client.delete(f"/api/agent-skills/{code}")
            self.assertEqual(deleted.status_code, 200, deleted.text)
            client.delete(f"/api/agent-skills/{imported_code}")

    def test_feedback_requires_and_preserves_user_reason(self) -> None:
        conn = connect()
        try:
            with self.assertRaises(BusinessError) as caught:
                create_feedback(conn, {"question": "测试问题", "answerSnippet": "测试总结", "reason": "   "})
            self.assertEqual(caught.exception.code, "VALIDATION_ERROR")

            created = create_feedback(conn, {"question": "测试问题", "answerSnippet": "测试总结", "reason": " 统计口径不正确 "})
            self.assertEqual(created["reason"], "统计口径不正确")
        finally:
            conn.rollback()
            conn.close()

    def test_run_ledger_endpoints_and_session_cleanup(self) -> None:
        conn = connect()
        session_id = create_session(conn, "run 台账测试")["id"]
        create_run(conn, session_id, "run-abc-123", f"session-{session_id}:run-abc-123", "测试问题")
        conn.commit()
        try:
            with TestClient(app) as client:
                listed = client.get(f"/api/qa/sessions/{session_id}/runs").json()["items"]
                self.assertTrue(any(item["runId"] == "run-abc-123" for item in listed))
                detail = client.get(f"/api/qa/sessions/{session_id}/runs/run-abc-123").json()
                self.assertEqual(detail["status"], "running")
                checkpoints = client.get(f"/api/qa/sessions/{session_id}/runs/run-abc-123/checkpoints").json()
                self.assertEqual(checkpoints["items"], [])
                deleted = client.delete(f"/api/qa/sessions/{session_id}")
                self.assertEqual(deleted.status_code, 200)
        finally:
            self.assertEqual(list_session_runs(conn, session_id), [])
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()
