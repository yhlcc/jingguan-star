from __future__ import annotations

from app.agent.context import AgentContext
from app.agent.playbooks import AnalysisSkill, skill_from_record, skill_summary
from app.agent.skill_matcher import select_skill
from app.agent.state import AgentState
from app.core.errors import BusinessError
from app.repositories.skills import enabled_skill_summaries, get_skill


def skill_matching(context: AgentContext, state: AgentState) -> dict:
    # 只加载轻量摘要用于匹配（code/name/description/triggerKeywords），不把全部 Skill 步骤塞进模型。
    catalog = enabled_skill_summaries(context.conn)
    skills = [
        AnalysisSkill(
            code=item["code"],
            name=item["name"],
            description=item["description"],
            trigger_keywords=tuple(str(kw) for kw in item.get("triggerKeywords", []) if str(kw).strip()),
            steps=(),
            instructions=str(item.get("instructions") or ""),
        )
        for item in catalog
    ]
    matched = select_skill(context, state["question"], state.get("entities", {}), skills)
    summary = None
    if matched is not None:
        # 命中后才按 code 加载完整 Skill（含步骤编排），避免匹配阶段把全部 Skill 体量塞进模型。
        try:
            skill = skill_from_record(get_skill(context.conn, matched.skill.code))
            summary = skill_summary(skill)
        except BusinessError:
            summary = None
    if summary:
        context.emit("skill", {"matched": True, "matchedBy": matched.method, "confidence": matched.confidence, "reason": matched.reason, **summary})
    else:
        context.emit("skill", {"matched": False, "message": "未命中固定业务 Skill，使用 LLM 动态规划兜底。"})
    return {"matched_skill": summary}
