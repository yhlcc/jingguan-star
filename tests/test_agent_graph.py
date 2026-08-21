from __future__ import annotations

import unittest

from app.agent.context import AgentContext
from app.agent.graph import resume_agent, run_agent
from app.agent.checkpointer import list_run_checkpoints
from app.agent.nodes.data_validation import data_validation
from app.agent.nodes.query_planning import _plan_from_raw, query_planning
from app.agent.playbooks import DEFAULT_SKILLS
from app.agent.step_ops import apply_transform
from app.agent.skill_matcher import match_by_vector
from app.core.database import connect
from app.core.errors import BusinessError
from app.repositories.runs import list_session_runs
from app.repositories.catalog import ensure_interface_approval_policy
from app.repositories.skills import get_skill, save_skill
from app.services.query_gateway import QueryGateway
from app.services.answer import answer_markdown
from app.services.llm import extract_json_string_field


class FakeLlm:
    stream_enabled = True

    def json(self, system: str, payload: dict) -> dict:
        if "意图识别" in system:
            return {"intent": "business_query", "entities": {"year": 2026}}
        if "Skill 选择器" in system:
            question = str(payload.get("question") or "")
            if "目标" in question or "缺口" in question:
                return {"skillCode": "goal.achievement.diagnosis", "confidence": 0.95, "reason": "目标与缺口"}
            if "产品" in question or "型号" in question:
                return {"skillCode": "product.contribution.analysis", "confidence": 0.92, "reason": "产品贡献"}
            return {"skillCode": "risk.impact.analysis", "confidence": 0.9, "reason": "风险商机"}
        if "Skill 编排器" in system:
            return {"rationale": "按自然语言流程编译计划", "calls": [
                {"callId": "queryA", "stepId": "queryA", "action": "interface", "interfaceCode": "biz.unitAchievement.query", "params": {"year": 2026}, "purpose": "查询 A"},
                {"callId": "topA", "stepId": "topA", "action": "derive", "dependsOn": ["queryA"], "transform": {"operation": "top", "fromStep": "queryA", "by": "incomeAmount", "limit": 3}, "purpose": "筛选 A 的 Top 结果"},
                {"callId": "queryB", "stepId": "queryB", "action": "interface", "interfaceCode": "biz.productModel.breakdown", "params": {"year": 2026}, "paramSources": {"productLines": {"fromStep": "topA", "path": "rows[].productLine", "unique": True, "limit": 3}}, "dependsOn": ["topA"], "purpose": "用 A 的派生结果查询 B"},
            ]}
        if "查询规划" in system:
            return {"rationale": "联合分析经营与风险", "calls": [
                {"callId": "overview", "interfaceCode": "biz.dashboard.summary", "params": {"year": 2026}, "purpose": "经营概览"},
                {"callId": "risk", "interfaceCode": "ledger.pplRisk.summary", "params": {"riskLevels": ["高"]}, "purpose": "风险商机"},
            ]}
        return {"dataFindings": ["经营与风险数据已完成联合分析。"], "visualization": {"metrics": ["totalIncomeAmount"]}, "nextSuggestions": ["按经营单元拆分"]}

    def stream_json(self, system: str, payload: dict, on_delta=None) -> dict:
        result = self.json(system, payload)
        answer = str(result.get("answer") or "好的")
        if on_delta:
            on_delta(answer)
        return result

    def stream_chat(self, messages: list, *, json_output: bool = False, on_delta=None) -> str:
        text = "## 分析结论\n整体经营平稳，风险商机需要关注。"
        if on_delta:
            on_delta(text)
        return text


class AgentGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = connect()
        self.events: list[tuple[str, dict]] = []
        self.context = AgentContext(self.conn, FakeLlm(), QueryGateway(self.conn), lambda name, data: self.events.append((name, data)), 2)  # type: ignore[arg-type]

    def tearDown(self) -> None:
        self.conn.rollback()
        self.conn.close()

    def test_skill_driven_multiple_interfaces(self) -> None:
        result = run_agent(self.context, session_id=1, question="整体经营情况和高风险商机怎么样", history=[])
        completed = [data["node"] for name, data in self.events if name == "node_completed"]
        self.assertEqual(completed, ["intent_recognition", "skill_matching", "query_planning", "whitelist_approval", "multi_interface_execute", "data_validation", "answer_generation"])
        self.assertEqual(result["matched_skill"]["code"], "risk.impact.analysis")
        self.assertGreaterEqual(len(result["approved_calls"]), 3)
        self.assertGreaterEqual(len(result["validated_results"]), 3)
        self.assertGreaterEqual(len(result["answer_payload"]["source"]["interfaces"]), 3)
        self.assertTrue(result["derived_metrics"]["items"])

    def test_goal_skill_generates_deterministic_multi_interface_plan(self) -> None:
        result = run_agent(self.context, session_id=1, question="今年目标完成情况和缺口在哪里", history=[])
        steps = [item["stepId"] for item in result["plan"]["calls"]]
        self.assertEqual(result["matched_skill"]["code"], "goal.achievement.diagnosis")
        self.assertEqual(steps, ["goal", "unitAchievement", "gapRanking", "productLine", "riskByGapUnits"])
        self.assertEqual(result["plan"]["calls"][4]["paramSources"]["unitNames"]["fromStep"], "gapRanking")
        self.assertTrue(any(item["interfaceCode"] == "skill.derive.gapRanking" for item in result["validated_results"]))

    def test_skill_step_can_feed_previous_result_into_next_interface(self) -> None:
        result = run_agent(self.context, session_id=1, question="哪些产品线收入占比最高", history=[])
        self.assertEqual(result["matched_skill"]["code"], "product.contribution.analysis")
        steps = {item.get("stepId"): item for item in result["validated_results"]}
        self.assertIn("topProductLines", steps)
        self.assertIn("modelBreakdown", steps)
        top_lines = {row["productLine"] for row in steps["topProductLines"]["rows"]}
        model_lines = {row["productLine"] for row in steps["modelBreakdown"]["rows"]}
        self.assertTrue(model_lines)
        self.assertTrue(model_lines.issubset(top_lines))

    def test_natural_language_skill_can_be_saved_without_steps(self) -> None:
        code = "custom.natural.workflow"
        save_skill(self.conn, code, {
            "skillCode": code,
            "skillName": "自然语言流程 Skill",
            "description": "用自然语言描述接口编排。",
            "instructions": "先查询 A，再根据 A 的返回值查询 B，最后合并结果形成结论。",
            "triggerKeywords": ["自然语言流程"],
            "steps": [],
            "status": "启用",
        }, create=True)
        saved = get_skill(self.conn, code)
        self.assertEqual(saved["instructions"], "先查询 A，再根据 A 的返回值查询 B，最后合并结果形成结论。")
        self.assertEqual(saved["steps"], [])

    def test_query_planning_compiles_natural_language_skill(self) -> None:
        result = query_planning(self.context, {
            "intent": "business_query",
            "question": "按自然语言流程分析 A 和 B",
            "history": [],
            "entities": {"year": 2026},
            "matched_skill": {
                "code": "custom.natural.workflow",
                "name": "自然语言流程 Skill",
                "description": "用自然语言描述接口编排。",
                "instructions": "先查询 A，筛选 Top 结果，再把结果作为条件查询 B。",
                "triggerKeywords": ["自然语言流程"],
                "steps": [],
                "derivedMetrics": [],
                "answerSections": [],
            },
        })
        calls = result["plan"]["calls"]
        self.assertEqual([call["stepId"] for call in calls], ["queryA", "topA", "queryB"])
        self.assertEqual(calls[1]["action"], "derive")
        self.assertEqual(calls[2]["paramSources"]["productLines"]["fromStep"], "topA")

    def test_query_planning_normalizes_null_optional_fields(self) -> None:
        plan = _plan_from_raw({"calls": [{
            "callId": "productLine",
            "stepId": "productLine",
            "action": "interface",
            "interfaceCode": "biz.productLine.analysis",
            "params": {"year": 2026},
            "paramSources": None,
            "transform": None,
            "dependsOn": None,
            "purpose": "查询产品线",
        }]})
        call = plan.model_dump(by_alias=True)["calls"][0]
        self.assertEqual(call["paramSources"], {})
        self.assertEqual(call["transform"], {})
        self.assertEqual(call["dependsOn"], [])

    def test_merge_rows_transform_combines_multiple_step_outputs(self) -> None:
        output = apply_transform("mergeABC", {
            "operation": "mergeRows",
            "base": {"fromStep": "queryA", "path": "rows", "as": "a"},
            "joins": [
                {"fromStep": "queryB", "path": "rows", "as": "b", "type": "left", "on": [["a.orgUnitName", "b.unitName"]]},
                {"fromStep": "queryC", "path": "rows", "as": "c", "type": "left", "on": [["a.orgUnitName", "c.unitName"]]},
            ],
            "select": {
                "unitName": "a.orgUnitName",
                "incomeAmount": "a.incomeAmount",
                "targetAmount": "b.targetAmount",
                "riskAmount": "c.riskAmount",
            },
            "computedFields": {
                "gapAmount": "targetAmount - incomeAmount",
                "riskToIncomeRatio": "riskAmount / incomeAmount",
            },
            "sortBy": "gapAmount",
            "order": "desc",
        }, {
            "queryA": {"rows": [{"orgUnitName": "华东", "incomeAmount": 80}, {"orgUnitName": "华南", "incomeAmount": 120}]},
            "queryB": {"rows": [{"unitName": "华东", "targetAmount": 100}, {"unitName": "华南", "targetAmount": 130}]},
            "queryC": {"rows": [{"unitName": "华东", "riskAmount": 8}, {"unitName": "华南", "riskAmount": 6}]},
        })
        self.assertEqual(output["rows"][0]["unitName"], "华东")
        self.assertEqual(output["rows"][0]["gapAmount"], 20)
        self.assertEqual(output["rows"][0]["riskToIncomeRatio"], 0.1)

    def test_whitelist_rejects_unknown_parameter(self) -> None:
        with self.assertRaises(BusinessError) as caught:
            self.context.gateway.approve("biz.dashboard.summary", {"sql": "DROP TABLE x"})
        self.assertEqual(caught.exception.code, "PARAM_NOT_ALLOWED")

    def test_data_validation_removes_unregistered_fields(self) -> None:
        update = data_validation(self.context, {"intent": "business_query", "execution_results": [{
            "interfaceCode": "biz.dashboard.summary", "rows": [{"totalIncomeAmount": 10, "secret": "blocked"}], "trace": {}
        }]})
        self.assertNotIn("secret", update["validated_results"][0]["rows"][0])
        self.assertIn("secret", update["validation_report"]["interfaces"][0]["removedFields"])

    def test_direct_chat_uses_same_graph_without_data_calls(self) -> None:
        result = run_agent(self.context, session_id=1, question="你好", history=[])
        self.assertEqual(result["intent"], "direct_chat")
        self.assertNotIn("approved_calls", result)
        self.assertEqual(result["answer_payload"]["type"], "directAnswer")

    def test_answer_places_statistics_between_table_and_visualization(self) -> None:
        markdown = answer_markdown({
            "dataFindings": ["已获取数据。"],
            "stats": {"rowCount": 3},
            "source": {"interfaces": [{"interfaceCode": "biz.test"}]},
        })
        self.assertLess(markdown.index("## 数据表格"), markdown.index("## 数据统计结果总结"))
        self.assertLess(markdown.index("## 数据统计结果总结"), markdown.index("## 数据可视化"))

    def test_vector_matching_selects_semantically_correct_skills(self) -> None:
        cases = {
            "整体经营情况和高风险商机怎么样": "risk.impact.analysis",
            "今年目标完成情况和缺口在哪里": "goal.achievement.diagnosis",
            "哪些产品线收入占比最高": "product.top-line.model-drilldown",
            "华东区域今年同比下滑的原因": "revenue.decline.attribution",
            "看看各经营单元的产品结构": "key.unit.drilldown",
        }
        for question, expected in cases.items():
            matched = match_by_vector(question, DEFAULT_SKILLS)
            self.assertIsNotNone(matched, question)
            self.assertEqual(matched.skill.code, expected, question)
        self.assertIsNone(match_by_vector("你好，今天天气怎么样", DEFAULT_SKILLS))

    def test_checkpointer_persists_run_and_snapshots(self) -> None:
        result = run_agent(self.context, session_id=1, question="整体经营情况和高风险商机怎么样", history=[])
        runs = list_session_runs(self.conn, 1)
        self.assertTrue(any(item["runId"] == result["trace_id"] and item["status"] == "completed" for item in runs))
        snapshots = list_run_checkpoints(1, result["trace_id"])
        self.assertGreaterEqual(len(snapshots), 5)
        self.assertEqual(snapshots[0]["state"]["matchedSkill"], "risk.impact.analysis")

    def test_human_approval_interrupts_then_resumes_from_checkpoint(self) -> None:
        ctx = AgentContext(self.conn, FakeLlm(), QueryGateway(self.conn), lambda name, data: self.events.append((name, data)), 2, require_approval=True)  # type: ignore[arg-type]
        state = run_agent(ctx, session_id=1, question="今年目标完成情况和缺口在哪里", history=[])
        self.assertIn("__interrupt__", state)
        run_id = state["trace_id"]
        calls = state["__interrupt__"][0].value["calls"]
        self.assertGreaterEqual(len(calls), 4)
        resumed = resume_agent(ctx, session_id=1, run_id=run_id, resume_value={"approved": True, "callIds": [call["callId"] for call in calls]})
        self.assertGreaterEqual(len(resumed["validated_results"]), 4)
        self.assertIn("final_answer", resumed)
        self.assertEqual([item["status"] for item in list_session_runs(self.conn, 1) if item["runId"] == run_id], ["completed"])

    def test_interface_policy_triggers_human_approval_without_global_switch(self) -> None:
        ensure_interface_approval_policy(self.conn)
        self.conn.execute("UPDATE ai_query_interface SET approval_policy='manual' WHERE interface_code='ledger.pplRisk.summary'")
        state = run_agent(self.context, session_id=1, question="整体经营情况和高风险商机怎么样", history=[])
        self.assertIn("__interrupt__", state)
        calls = state["__interrupt__"][0].value["calls"]
        self.assertEqual([call["interfaceCode"] for call in calls], ["ledger.pplRisk.summary"])

    def test_human_approval_empty_call_ids_rejects_all_calls(self) -> None:
        ctx = AgentContext(self.conn, FakeLlm(), QueryGateway(self.conn), lambda name, data: self.events.append((name, data)), 2, require_approval=True)  # type: ignore[arg-type]
        state = run_agent(ctx, session_id=1, question="今年目标完成情况和缺口在哪里", history=[])
        with self.assertRaises(BusinessError):
            resume_agent(ctx, session_id=1, run_id=state["trace_id"], resume_value={"approved": True, "callIds": []})

    def test_progressive_json_answer_extraction(self) -> None:
        full = '{"answer": "你好\\n世界", "nextSuggestions": ["继续"]}'
        text = ""
        extracted = ""
        for char in full:
            text += char
            prefix = extract_json_string_field(text, "answer")
            if len(prefix) > len(extracted):
                extracted = prefix
        self.assertEqual(extracted, "你好\n世界")
        self.assertEqual(extract_json_string_field('{"other": 1}', "answer"), "")
        self.assertEqual(extract_json_string_field('{"answer": "\\u4f60', "answer"), "你")


if __name__ == "__main__":
    unittest.main()
