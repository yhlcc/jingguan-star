from __future__ import annotations

import uuid

from app.agent.context import AgentContext
from app.agent.playbooks import plan_from_skill, skill_from_record
from app.agent.state import AgentState, PlannedCall, QueryPlan
from app.core.errors import ModelError
from app.repositories.catalog import interface_specs


def query_planning(context: AgentContext, state: AgentState) -> dict:
    if state.get("intent") == "direct_chat": return {"plan": QueryPlan().model_dump(by_alias=True)}
    matched = state.get("matched_skill") or {}
    if matched.get("code"):
        skill = skill_from_record(matched)
        if skill.steps:
            plan = plan_from_skill(skill, state)
        elif skill.instructions.strip():
            plan = _plan_from_skill_instructions(context, state, matched)
        else:
            plan = QueryPlan(rationale=f"命中业务 Skill：{skill.name}，但该 Skill 尚未配置流程说明或编排步骤。")
        context.emit("plan", {"rationale": plan.rationale, "calls": [call.model_dump(by_alias=True) for call in plan.calls]})
        return {"plan": plan.model_dump(by_alias=True)}
    plan = _dynamic_plan(context, state)
    context.emit("plan", {"rationale": plan.rationale, "calls": [call.model_dump(by_alias=True) for call in plan.calls]})
    return {"plan": plan.model_dump(by_alias=True)}


def _plan_from_skill_instructions(context: AgentContext, state: AgentState, matched: dict) -> QueryPlan:
    specs = interface_specs(context.conn, only_enabled=True)
    try:
        result = context.llm.json(
            "你是经营分析 Skill 编排器。根据命中的自然语言 Skill 流程，把业务说明编译成可执行计划。"
            "只能使用给定白名单接口；接口调用之外的合并、筛选、排序、计算必须写成 derive/transform 步骤。只返回 JSON。",
            {"question": state["question"], "conversationHistory": state.get("history", []), "entities": state.get("entities", {}),
             "matchedSkill": {
                 "code": matched.get("code"),
                 "name": matched.get("name"),
                 "description": matched.get("description"),
                 "instructions": matched.get("instructions"),
                 "derivedMetrics": matched.get("derivedMetrics", []),
                 "answerSections": matched.get("answerSections", []),
             },
             "availableInterfaces": specs,
             "outputSchema": {
                 "rationale": "规划理由",
                 "calls": [
                     {
                         "callId": "唯一ID",
                         "stepId": "稳定步骤ID",
                         "action": "interface|derive",
                         "interfaceCode": "接口步骤填写白名单编码；derive 步骤为 null",
                         "params": {},
                         "paramSources": {"参数名": {"fromStep": "前置 stepId", "path": "rows[].字段", "unique": True, "limit": 20}},
                         "dependsOn": ["前置 stepId"],
                         "transform": {"operation": "selectDistinct|top|filterRows|computeGap|aggregate|mergeRows", "fromStep": "前置 stepId"},
                         "purpose": "该步骤的业务目的",
                     }
                 ],
             },
             "rules": [
                 "默认年份为2026；优先使用 entities 中的年份、经营单元、行业、产品和阶段",
                 "不得生成 SQL、表名或数据库字段之外的自由查询",
                 "interface 步骤只能调用 availableInterfaces 中的 interfaceCode",
                 "当后续接口需要前序结果作为入参时，用 dependsOn 和 paramSources 表达",
                 "当流程要求合并、筛选、排序、计算时，用 derive 步骤表达，不要把计算藏在自然语言回答里",
                 "derive 只能使用当前执行器支持的 operation：selectDistinct、top、filterRows、computeGap、aggregate、mergeRows",
                 "mergeRows 用于跨多个步骤做 left join、字段选择和四则运算；格式包含 base、joins、select、computedFields、sortBy、order、limit",
                 "步骤按执行顺序返回，依赖步骤必须排在使用者之前",
                 "最多8个步骤",
             ]},
        )
    except ModelError:
        return QueryPlan(calls=[], rationale=f"命中业务 Skill：{matched.get('name')}，但模型暂不可用，无法把自然语言流程编译成执行计划。")
    return _plan_from_raw(result, fallback_rationale=f"命中业务 Skill：{matched.get('name')}，按自然语言流程生成查询计划。", limit=8)


def _dynamic_plan(context: AgentContext, state: AgentState) -> QueryPlan:
    specs = interface_specs(context.conn, only_enabled=True)
    result = context.llm.json(
        "你是经营数据查询规划器。只能从给定白名单接口中规划调用；可为一个问题规划多个互补接口。只返回 JSON。",
        {"question": state["question"], "conversationHistory": state.get("history", []), "entities": state.get("entities", {}),
         "availableInterfaces": specs,
         "outputSchema": {"rationale": "规划理由", "calls": [{"callId": "唯一ID", "interfaceCode": "白名单编码", "params": {}, "purpose": "该调用回答什么"}]},
         "rules": ["默认年份为2026", "不得生成SQL、表名或数据库字段", "整体指标与风险、产品或行业组合问题应规划多个接口", "最多4个调用"]},
    )
    return _plan_from_raw(result, limit=4)


def _plan_from_raw(result: dict, fallback_rationale: str = "", limit: int = 4) -> QueryPlan:
    raw_calls = result.get("calls") if isinstance(result.get("calls"), list) else []
    calls = []
    for item in raw_calls[:limit]:
        if not isinstance(item, dict): continue
        item = _normalize_call(item)
        item.setdefault("callId", uuid.uuid4().hex[:12])
        item.setdefault("action", "interface" if item.get("interfaceCode") else "derive")
        calls.append(PlannedCall.model_validate(item))
    return QueryPlan(calls=calls, rationale=str(result.get("rationale") or fallback_rationale))


def _normalize_call(item: dict) -> dict:
    normalized = dict(item)
    for key in ("params", "paramSources", "transform"):
        if not isinstance(normalized.get(key), dict):
            normalized[key] = {}
    if not isinstance(normalized.get("dependsOn"), list):
        normalized["dependsOn"] = []
    if normalized.get("interfaceCode") in ("", None):
        normalized["interfaceCode"] = None
    return normalized
