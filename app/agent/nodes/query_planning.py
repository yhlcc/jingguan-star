from __future__ import annotations

import uuid

from app.agent.context import AgentContext
from app.agent.playbooks import plan_from_skill, skill_from_record
from app.agent.state import AgentState, PlannedCall, QueryPlan
from app.repositories.catalog import interface_specs


def query_planning(context: AgentContext, state: AgentState) -> dict:
    if state.get("intent") == "direct_chat": return {"plan": QueryPlan().model_dump(by_alias=True)}
    matched = state.get("matched_skill") or {}
    if matched.get("code"):
        skill = skill_from_record(matched)
        plan = plan_from_skill(skill, state)
        context.emit("plan", {"rationale": plan.rationale, "calls": [call.model_dump(by_alias=True) for call in plan.calls]})
        return {"plan": plan.model_dump(by_alias=True)}
    specs = interface_specs(context.conn, only_enabled=True)
    result = context.llm.json(
        "你是经营数据查询规划器。只能从给定白名单接口中规划调用；可为一个问题规划多个互补接口。只返回 JSON。",
        {"question": state["question"], "conversationHistory": state.get("history", []), "entities": state.get("entities", {}),
         "availableInterfaces": specs,
         "outputSchema": {"rationale": "规划理由", "calls": [{"callId": "唯一ID", "interfaceCode": "白名单编码", "params": {}, "purpose": "该调用回答什么"}]},
         "rules": ["默认年份为2026", "不得生成SQL、表名或数据库字段", "整体指标与风险、产品或行业组合问题应规划多个接口", "最多4个调用"]},
    )
    raw_calls = result.get("calls") if isinstance(result.get("calls"), list) else []
    calls = []
    for item in raw_calls[:4]:
        if not isinstance(item, dict): continue
        item.setdefault("callId", uuid.uuid4().hex[:12])
        calls.append(PlannedCall.model_validate(item))
    plan = QueryPlan(calls=calls, rationale=str(result.get("rationale") or ""))
    context.emit("plan", {"rationale": plan.rationale, "calls": [call.model_dump(by_alias=True) for call in plan.calls]})
    return {"plan": plan.model_dump(by_alias=True)}
