from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent.state import PlannedCall, QueryPlan


@dataclass(frozen=True)
class PlaybookStep:
    step_id: str
    action: str = "interface"
    interface_code: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    param_sources: dict[str, Any] = field(default_factory=dict)
    transform: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    purpose: str = ""


@dataclass(frozen=True)
class AnalysisSkill:
    code: str
    name: str
    description: str
    trigger_keywords: tuple[str, ...]
    steps: tuple[PlaybookStep, ...]
    instructions: str = ""
    derived_metrics: tuple[str, ...] = ()
    answer_sections: tuple[str, ...] = ()


DEFAULT_SKILLS: tuple[AnalysisSkill, ...] = (
    AnalysisSkill(
        code="goal.achievement.diagnosis",
        name="经营目标达成诊断",
        description="用于回答目标完成率、收入缺口、未达成单元和风险影响。",
        trigger_keywords=("目标", "达成", "完成率", "完成情况", "缺口", "差距"),
        steps=(
            PlaybookStep("goal", interface_code="ledger.goal.query", params={"year": "$year", "unitNames": "$units"}, purpose="查询经营目标"),
            PlaybookStep("unitAchievement", interface_code="biz.unitAchievement.query", params={"year": "$year", "unitNames": "$units"}, purpose="查询经营单元收入达成"),
            PlaybookStep(
                "gapRanking",
                action="derive",
                transform={
                    "operation": "computeGap",
                    "fromStep": "unitAchievement",
                    "targetField": "targetAmount",
                    "actualField": "incomeAmount",
                    "outputField": "gapAmount",
                    "dimensionFields": ["orgUnitName"],
                    "positiveOnly": True,
                    "sortBy": "gapAmount",
                    "order": "desc",
                    "limit": 10,
                },
                depends_on=("unitAchievement",),
                purpose="计算目标缺口并输出未达成单元排名",
            ),
            PlaybookStep("productLine", interface_code="biz.productLine.analysis", params={"year": "$year", "productLines": "$products"}, purpose="拆解产品线贡献"),
            PlaybookStep(
                "riskByGapUnits",
                interface_code="ledger.pplRisk.summary",
                params={"riskLevels": ["高"]},
                param_sources={"unitNames": {"fromStep": "gapRanking", "path": "rows[].orgUnitName", "unique": True, "limit": 20}},
                depends_on=("gapRanking",),
                purpose="用未达成单元作为条件评估高风险商机影响",
            ),
        ),
        derived_metrics=("gapAmount", "completionRate", "riskExposureAmount"),
        answer_sections=("目标完成概览", "缺口单元排名", "产品线贡献", "风险影响", "建议动作"),
    ),
    AnalysisSkill(
        code="revenue.decline.attribution",
        name="收入下滑归因分析",
        description="用于回答收入下降、同比变化、行业和产品线归因。",
        trigger_keywords=("下滑", "下降", "同比", "增长", "归因", "原因"),
        steps=(
            PlaybookStep("overview", interface_code="biz.dashboard.summary", params={"year": "$year"}, purpose="查询整体收入和同比"),
            PlaybookStep("unitAchievement", interface_code="biz.unitAchievement.query", params={"year": "$year", "unitNames": "$units"}, purpose="定位经营单元变化"),
            PlaybookStep("productLine", interface_code="biz.productLine.analysis", params={"year": "$year", "productLines": "$products"}, purpose="定位产品线变化"),
            PlaybookStep("industry", interface_code="biz.industryAchievement.query", params={"year": "$year", "industryNames": "$industries"}, purpose="定位行业变化"),
        ),
        derived_metrics=("yoyRate", "negativeContribution", "rankByIncome"),
        answer_sections=("整体变化", "单元归因", "产品归因", "行业归因", "建议动作"),
    ),
    AnalysisSkill(
        code="key.unit.drilldown",
        name="重点经营单元穿透分析",
        description="用于分析某个经营单元的收入、产品结构和台账聚合。",
        trigger_keywords=("经营单元", "重点单元", "单元", "区域", "部门"),
        steps=(
            PlaybookStep("unitAchievement", interface_code="biz.unitAchievement.query", params={"year": "$year", "unitNames": "$units"}, purpose="查询单元达成"),
            PlaybookStep("keyUnitProduct", interface_code="biz.keyUnitProduct.analysis", params={"year": "$year", "unitNames": "$units", "productLines": "$products"}, purpose="穿透单元产品贡献"),
            PlaybookStep("commercialByProduct", interface_code="ledger.commercial.aggregate", params={"year": "$year", "dimensions": ["productLine"], "metrics": ["incomeAmount", "orderAmount", "recordCount"]}, purpose="按产品线聚合台账"),
        ),
        derived_metrics=("unitCompletionRank", "productContribution"),
        answer_sections=("单元概览", "产品穿透", "台账聚合", "建议动作"),
    ),
    AnalysisSkill(
        code="risk.impact.analysis",
        name="高风险商机影响分析",
        description="用于回答 PPL 风险商机、风险金额、风险阶段和对经营目标的影响。",
        trigger_keywords=("风险", "商机", "PPL", "ppl", "管道", "高风险"),
        steps=(
            PlaybookStep("riskSummary", interface_code="ledger.pplRisk.summary", params={"riskLevels": ["高"], "unitNames": "$units", "projectStages": "$stages"}, purpose="统计高风险商机"),
            PlaybookStep("overview", interface_code="biz.dashboard.summary", params={"year": "$year"}, purpose="查询整体经营基准"),
            PlaybookStep(
                "affectedUnits",
                action="derive",
                transform={"operation": "selectDistinct", "fromStep": "riskSummary", "field": "unitName", "as": "unitName", "limit": 20},
                depends_on=("riskSummary",),
                purpose="从高风险商机中提取受影响经营单元",
            ),
            PlaybookStep(
                "unitAchievement",
                interface_code="biz.unitAchievement.query",
                params={"year": "$year"},
                param_sources={"unitNames": {"fromStep": "affectedUnits", "path": "rows[].unitName", "unique": True, "limit": 20}},
                depends_on=("affectedUnits",),
                purpose="用风险商机涉及单元作为条件查询经营达成",
            ),
        ),
        derived_metrics=("riskExposureAmount", "riskProjectCount", "riskToIncomeRatio"),
        answer_sections=("风险概览", "阶段分布", "经营影响", "建议动作"),
    ),
    AnalysisSkill(
        code="product.contribution.analysis",
        name="产品线贡献分析",
        description="用于回答产品结构、产品线贡献和型号明细。",
        trigger_keywords=("产品", "产品线", "型号", "结构", "贡献", "占比"),
        steps=(
            PlaybookStep("productLine", interface_code="biz.productLine.analysis", params={"year": "$year", "productLines": "$products"}, purpose="查询产品线收入贡献"),
            PlaybookStep(
                "topProductLines",
                action="derive",
                transform={"operation": "top", "fromStep": "productLine", "by": "amount", "order": "desc", "limit": 3},
                depends_on=("productLine",),
                purpose="筛选收入最高的产品线",
            ),
            PlaybookStep(
                "modelBreakdown",
                interface_code="biz.productModel.breakdown",
                params={"year": "$year"},
                param_sources={"productLines": {"fromStep": "topProductLines", "path": "rows[].productLine", "unique": True, "limit": 3}},
                depends_on=("topProductLines",),
                purpose="用 Top 产品线作为条件查询型号明细",
            ),
            PlaybookStep("unitAchievement", interface_code="biz.unitAchievement.query", params={"year": "$year", "unitNames": "$units"}, purpose="关联经营单元达成"),
        ),
        derived_metrics=("productContribution", "modelShareRate"),
        answer_sections=("产品线贡献", "型号明细", "单元关联", "建议动作"),
    ),
    AnalysisSkill(
        code="product.top-line.model-drilldown",
        name="Top 产品线型号下钻分析",
        description="用于回答哪些产品线贡献最高、重点产品线下面哪些型号贡献最大、产品结构是否集中等问题。",
        trigger_keywords=("产品线下钻", "型号下钻", "Top产品线", "产品结构", "型号贡献", "产品线贡献"),
        steps=(),
        instructions=(
            "当用户询问产品线贡献、产品结构集中度、重点产品线下的型号表现时使用。\n"
            "流程：\n"
            "1. 先调用 biz.productLine.analysis 查询当年产品线完成金额、对比金额和同比，参数 year 来自用户问题，productLines 可来自用户显式指定的产品线。\n"
            "2. 增加 derive 步骤，使用 top 操作从 biz.productLine.analysis 的 rows 中按 amount 倒序筛选 Top 3 产品线，字段路径为 rows[].productLine。\n"
            "3. 再调用 biz.productModel.breakdown，把上一步 Top 产品线通过 paramSources 传给 productLines 参数，dependsOn 指向 Top 产品线派生步骤。\n"
            "4. 如用户同时提到经营单元或区域，可补充调用 biz.unitAchievement.query 做单元达成背景，但型号下钻必须以产品线 Top 结果为条件。\n"
            "5. 回答时先说明产品线贡献排名，再说明 Top 产品线下的型号明细、占比和同比变化，最后给出是否存在产品集中风险或增长机会。"
        ),
        derived_metrics=("topProductContribution", "modelShareRate", "productConcentration"),
        answer_sections=("产品线贡献排名", "Top 产品线筛选条件", "型号下钻结果", "结构风险与机会"),
    ),
    AnalysisSkill(
        code="unit.goal-gap.risk-merge-diagnosis",
        name="经营单元目标缺口与风险敞口诊断",
        description="用于回答经营单元目标缺口、收入完成、风险商机敞口如何共同影响目标达成的问题。",
        trigger_keywords=("目标缺口风险", "经营单元风险", "风险敞口", "缺口诊断", "目标风险影响", "单元综合诊断"),
        steps=(),
        instructions=(
            "当用户询问哪些经营单元存在目标缺口、风险商机是否影响达成、缺口和风险需要一起排序诊断时使用。\n"
            "流程：\n"
            "1. 调用 biz.unitAchievement.query 查询经营单元收入、目标、完成率和同比，参数 year 来自用户问题，unitNames 来自用户指定的经营单元。\n"
            "2. 调用 ledger.goal.query 查询经营单元商业目标和商解目标，参数 year 与 unitNames 保持一致。\n"
            "3. 调用 ledger.pplRisk.summary 查询高风险商机，riskLevels 固定为 [\"高\"]，如用户指定经营单元或阶段则同步传入 unitNames、projectStages。\n"
            "4. 在三个接口返回后增加 derive 步骤，使用 mergeRows 做经营单元维度合并：以 biz.unitAchievement.query 的 rows 为 base，别名 ua；按 ua.orgUnitName = goal.unitName 关联 ledger.goal.query，按 ua.orgUnitName = risk.unitName 关联 ledger.pplRisk.summary。\n"
            "5. mergeRows 的 select 至少输出 unitName、incomeAmount、targetAmount、completionRate、commercialTargetAmount、solutionTargetAmount、riskAmount、riskProjectCount。\n"
            "6. mergeRows 的 computedFields 至少计算 gapAmount = targetAmount - incomeAmount、goalLedgerAmount = commercialTargetAmount + solutionTargetAmount、riskToIncomeRatio = riskAmount / incomeAmount。\n"
            "7. 合并结果按 gapAmount desc 排序，限制前 20 条；如果用户强调风险优先，则按 riskToIncomeRatio desc 排序。\n"
            "8. 最终回答必须优先使用合并后的 derive 结果指出“缺口大且风险高”的经营单元，再补充单接口概览和建议动作。"
        ),
        derived_metrics=("gapAmount", "goalLedgerAmount", "riskToIncomeRatio", "riskProjectCount"),
        answer_sections=("目标与收入概览", "缺口和风险合并排名", "重点经营单元诊断", "建议动作"),
    ),
)


def match_skill(question: str, entities: dict[str, Any], skills: list[AnalysisSkill] | tuple[AnalysisSkill, ...] = DEFAULT_SKILLS) -> AnalysisSkill | None:
    text = question.lower()
    scored: list[tuple[int, AnalysisSkill]] = []
    for skill in skills:
        score = sum(1 for keyword in skill.trigger_keywords if keyword.lower() in text)
        if skill.code == "goal.achievement.diagnosis" and entities.get("year"):
            score += 1 if any(word in text for word in ("目标", "完成", "达成")) else 0
        if score:
            scored.append((score, skill))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def skill_summary(skill: AnalysisSkill | None) -> dict[str, Any] | None:
    if skill is None:
        return None
    return {
        "code": skill.code,
        "name": skill.name,
        "description": skill.description,
        "instructions": skill.instructions,
        "triggerKeywords": list(skill.trigger_keywords),
        "derivedMetrics": list(skill.derived_metrics),
        "answerSections": list(skill.answer_sections),
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
    }


def plan_from_skill(skill: AnalysisSkill, state: dict[str, Any]) -> QueryPlan:
    calls: list[PlannedCall] = []
    for index, step in enumerate(skill.steps, 1):
        params = _resolve_params(step.params, state)
        calls.append(
            PlannedCall(
                stepId=step.step_id,
                action=step.action,
                callId=f"{skill.code}.{index}",
                interfaceCode=step.interface_code,
                params=params,
                paramSources=step.param_sources,
                transform=step.transform,
                dependsOn=list(step.depends_on),
                purpose=step.purpose,
            )
        )
    return QueryPlan(calls=calls, rationale=f"命中业务 Skill：{skill.name}，按固定经营分析路径执行多接口查询。")


def skill_by_code(code: str, skills: list[AnalysisSkill] | tuple[AnalysisSkill, ...] = DEFAULT_SKILLS) -> AnalysisSkill | None:
    return next((skill for skill in skills if skill.code == code), None)


def skill_from_record(record: dict[str, Any]) -> AnalysisSkill:
    return AnalysisSkill(
        code=str(record.get("skillCode") or record["code"]),
        name=str(record.get("skillName") or record["name"]),
        description=str(record.get("description") or ""),
        trigger_keywords=tuple(str(item) for item in record.get("triggerKeywords", []) if str(item).strip()),
        steps=tuple(
            PlaybookStep(
                step_id=str(item.get("stepId") or item.get("id") or item.get("interfaceCode") or f"step{index}"),
                action=str(item.get("action") or ("interface" if item.get("interfaceCode") else "derive")),
                interface_code=str(item["interfaceCode"]) if item.get("interfaceCode") else None,
                params=dict(item.get("params") or {}),
                param_sources=dict(item.get("paramSources") or item.get("param_sources") or {}),
                transform=dict(item.get("transform") or {}),
                depends_on=tuple(str(value) for value in item.get("dependsOn", []) if str(value).strip()) if isinstance(item.get("dependsOn"), list) else (),
                purpose=str(item.get("purpose") or ""),
            )
            for index, item in enumerate(record.get("steps", []), 1)
            if isinstance(item, dict) and item.get("interfaceCode")
            or isinstance(item, dict) and item.get("action") in {"derive", "transform"}
        ),
        instructions=str(record.get("instructions") or ""),
        derived_metrics=tuple(str(item) for item in record.get("derivedMetrics", []) if str(item).strip()),
        answer_sections=tuple(str(item) for item in record.get("answerSections", []) if str(item).strip()),
    )


def _resolve_params(template: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for key, value in template.items():
        concrete = _resolve_value(value, state)
        if concrete not in (None, "", []):
            resolved[key] = concrete
    return resolved


def _resolve_value(value: Any, state: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        if value.startswith("$steps.") or value.startswith("$entities."):
            return value
        return _entity_value(value[1:], state)
    if isinstance(value, list):
        return [_resolve_value(item, state) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_value(item, state) for key, item in value.items()}
    return value


def _entity_value(name: str, state: dict[str, Any]) -> Any:
    entities = state.get("entities") or {}
    aliases = {
        "year": ("year",),
        "units": ("units", "unitNames"),
        "industries": ("industries", "industryNames"),
        "products": ("products", "productLines"),
        "stages": ("stages", "projectStages"),
    }
    for key in aliases.get(name, (name,)):
        value = entities.get(key)
        if value not in (None, "", []):
            return value
    if name == "year":
        return 2026
    return None
