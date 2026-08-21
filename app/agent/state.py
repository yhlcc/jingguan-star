from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class PlannedCall(BaseModel):
    call_id: str = Field(alias="callId")
    step_id: str | None = Field(default=None, alias="stepId")
    action: str = "interface"
    interface_code: str | None = Field(default=None, alias="interfaceCode")
    params: dict[str, Any] = Field(default_factory=dict)
    param_sources: dict[str, Any] = Field(default_factory=dict, alias="paramSources")
    transform: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")
    purpose: str = ""

    model_config = {"populate_by_name": True}


class QueryPlan(BaseModel):
    calls: list[PlannedCall] = Field(default_factory=list)
    rationale: str = ""


class AgentState(TypedDict, total=False):
    trace_id: str
    session_id: int
    question: str
    history: list[dict[str, str]]
    intent: Literal["business_query", "direct_chat"]
    entities: dict[str, Any]
    matched_skill: dict[str, Any] | None
    plan: dict[str, Any]
    approved_calls: list[dict[str, Any]]
    rejected_calls: list[dict[str, Any]]
    execution_results: list[dict[str, Any]]
    execution_errors: list[dict[str, Any]]
    step_outputs: dict[str, dict[str, Any]]
    validated_results: list[dict[str, Any]]
    validation_report: dict[str, Any]
    derived_metrics: dict[str, Any]
    final_answer: str
    answer_payload: dict[str, Any]


NODE_LABELS = {
    "intent_recognition": "意图识别",
    "skill_matching": "业务 Skill 匹配",
    "query_planning": "查询计划",
    "whitelist_approval": "白名单审批",
    "multi_interface_execute": "多接口执行",
    "data_validation": "数据校验",
    "answer_generation": "回答生成",
}
