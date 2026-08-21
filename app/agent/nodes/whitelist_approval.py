from __future__ import annotations

from langgraph.types import interrupt

from app.agent.context import AgentContext
from app.agent.state import AgentState
from app.core.errors import BusinessError
from app.repositories.catalog import interface_requires_approval


def whitelist_approval(context: AgentContext, state: AgentState) -> dict:
    calls = list(state.get("plan", {}).get("calls", []))
    pending_approval_calls = [call for call in calls if _requires_human_approval(context, call)]
    if pending_approval_calls:
        decision = interrupt({
            "message": "以下高风险接口调用需要人工审批",
            "calls": [
                {
                    "callId": call.get("callId"),
                    "stepId": call.get("stepId"),
                    "action": call.get("action", "interface"),
                    "interfaceCode": call.get("interfaceCode"),
                    "params": call.get("params", {}),
                    "paramSources": call.get("paramSources", {}),
                    "transform": call.get("transform", {}),
                    "dependsOn": call.get("dependsOn", []),
                    "purpose": call.get("purpose"),
                }
                for call in pending_approval_calls
            ],
        })
        if not isinstance(decision, dict) or decision.get("approved") is not True:
            raise BusinessError("QUERY_PLAN_REJECTED", "查询计划未通过人工审批，已取消本次查询。")
        approved_ids = decision.get("callIds") if isinstance(decision.get("callIds"), list) else None
        if approved_ids is not None:
            pending_ids = {call.get("callId") for call in pending_approval_calls}
            approved_id_set = set(approved_ids)
            if context.require_approval and not approved_id_set:
                raise BusinessError("QUERY_PLAN_REJECTED", "查询计划未通过人工审批，已取消本次查询。")
            calls = [call for call in calls if call.get("callId") not in pending_ids or call.get("callId") in approved_id_set]
    approved, rejected = [], []
    for call in calls:
        try:
            if call.get("action") in {"derive", "transform"}:
                approved.append({**call, "approval": "approved"})
                continue
            code = str(call.get("interfaceCode") or "")
            if _has_dynamic_inputs(call):
                context.gateway.ensure_executable(code)
                approved.append({**call, "approval": "approved", "paramsDeferred": True})
            else:
                params = context.gateway.approve(code, dict(call.get("params") or {}))
                approved.append({**call, "params": params, "approval": "approved"})
        except BusinessError as exc:
            rejected.append({**call, "approval": "rejected", "reason": exc.message, "code": exc.code})
    if state.get("intent") == "business_query" and not approved:
        reason = rejected[0]["reason"] if rejected else "查询计划中没有可执行接口"
        raise BusinessError("QUERY_PLAN_REJECTED", reason)
    return {"approved_calls": approved, "rejected_calls": rejected}


def _requires_human_approval(context: AgentContext, call: dict) -> bool:
    if call.get("action") in {"derive", "transform"}:
        return False
    code = str(call.get("interfaceCode") or "")
    if not code:
        return False
    return context.require_approval or interface_requires_approval(context.conn, code)


def _has_dynamic_inputs(call: dict) -> bool:
    if call.get("paramSources"):
        return True
    return _contains_step_ref(call.get("params"))


def _contains_step_ref(value) -> bool:
    if isinstance(value, str):
        return value.startswith("$steps.")
    if isinstance(value, list):
        return any(_contains_step_ref(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_step_ref(item) for item in value.values())
    return False
