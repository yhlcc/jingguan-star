from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from app.agent.context import AgentContext
from app.agent.playbooks import AnalysisSkill, match_skill
from app.core.config import settings
from app.core.errors import ModelError


@dataclass(frozen=True)
class SkillMatch:
    skill: AnalysisSkill
    method: str
    confidence: float
    reason: str = ""


def compact_catalog(skills: list[AnalysisSkill]) -> list[dict[str, Any]]:
    """Only code/name/description/keywords go into the model prompt; steps stay out until matched."""
    return [
        {
            "code": skill.code,
            "name": skill.name,
            "description": skill.description,
            "instructions": skill.instructions[:600] if skill.instructions else "",
            "triggerKeywords": list(skill.trigger_keywords),
        }
        for skill in skills
    ]


def match_by_llm(context: AgentContext, question: str, skills: list[AnalysisSkill]) -> SkillMatch | None:
    """Semantic selection: skill descriptions are placed inside the agent prompt, then the LLM picks one."""
    if not skills:
        return None
    try:
        result = context.llm.json(
            "你是经营分析 Skill 选择器。根据用户问题从候选 Skill 中选出语义上最匹配的一个；"
            "仅当某个 Skill 的描述明确覆盖该问题时才选择，否则返回 null。不要编造候选列表之外的 skillCode。只返回 JSON。",
            {
                "question": question,
                "candidateSkills": compact_catalog(skills),
                "outputSchema": {"skillCode": "选中 Skill 的 code 或 null", "confidence": "0.0-1.0 置信度", "reason": "一句话选择理由"},
                "rules": [
                    "结合名称、描述与触发词做语义判断，而不是只按关键词计数",
                    "候选列表为空或不匹配时 skillCode 必须为 null",
                    "‘目标完成率、缺口、差距’优先选 goal.achievement.diagnosis",
                    "‘同比下滑、增长、归因’优先选 revenue.decline.attribution",
                    "‘某经营单元/区域/部门表现’优先选 key.unit.drilldown",
                    "‘PPL、风险商机、风险金额’优先选 risk.impact.analysis",
                    "‘产品结构、型号、占比’优先选 product.contribution.analysis",
                ],
            },
        )
    except ModelError:
        return None
    code = result.get("skillCode") or result.get("code")
    if not code:
        return None
    skill = next((item for item in skills if item.code == code), None)
    if skill is None:
        return None
    try:
        confidence = float(result.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return SkillMatch(
        skill=skill,
        method="llm",
        confidence=max(0.0, min(confidence, 1.0)),
        reason=str(result.get("reason") or "LLM 语义匹配"),
    )


def match_by_vector(question: str, skills: list[AnalysisSkill], threshold: float | None = None) -> SkillMatch | None:
    """Vector-space retrieval over character n-gram TF-IDF (offline, no extra dependencies)."""
    threshold = settings.skill_vector_threshold if threshold is None else threshold
    if not skills or not question.strip():
        return None
    index = _TfidfIndex(skills)
    best, best_score = index.best_match(question)
    if best is None or best_score < threshold:
        return None
    return SkillMatch(skill=best, method="vector", confidence=round(best_score, 4), reason="向量相似度召回")


def match_by_keyword(question: str, entities: dict[str, Any], skills: list[AnalysisSkill]) -> SkillMatch | None:
    skill = match_skill(question, entities, skills)
    if skill is None:
        return None
    return SkillMatch(skill=skill, method="keyword", confidence=0.0, reason="关键词兜底")


def select_skill(
    context: AgentContext,
    question: str,
    entities: dict[str, Any],
    skills: list[AnalysisSkill],
) -> SkillMatch | None:
    """Primary: LLM semantic selection. Fallbacks: vector retrieval, then keyword scoring."""
    mode = settings.skill_match
    if mode in ("auto", "llm"):
        matched = match_by_llm(context, question, skills)
        if matched:
            return matched
    if mode in ("auto", "vector"):
        matched = match_by_vector(question, skills)
        if matched:
            return matched
    if mode in ("auto", "keyword"):
        return match_by_keyword(question, entities, skills)
    return None


_WORD_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens: list[str] = _WORD_RE.findall(text)
    cjk = _CJK_RE.findall(text)
    tokens.extend(cjk)
    tokens.extend("".join(pair) for pair in zip(cjk, cjk[1:]))
    return tokens


class _TfidfIndex:
    def __init__(self, skills: list[AnalysisSkill]) -> None:
        docs = [_tokenize(f"{skill.name} {skill.description} {' '.join(skill.trigger_keywords)}") for skill in skills]
        self.skills = skills
        self.vectors = [_TfidfIndex._tf(terms) for terms in docs]
        document_frequency: dict[str, int] = {}
        for terms in docs:
            for term in set(terms):
                document_frequency[term] = document_frequency.get(term, 0) + 1
        n = len(skills)
        self.idf = {
            term: math.log((1 + n) / (1 + freq)) + 1.0
            for term, freq in document_frequency.items()
        }
        self.norms = [_TfidfIndex._norm(vec) for vec in self.vectors]

    @staticmethod
    def _tf(terms: list[str]) -> dict[str, float]:
        counts: dict[str, float] = {}
        for term in terms:
            counts[term] = counts.get(term, 0.0) + 1.0
        return counts

    @staticmethod
    def _norm(vector: dict[str, float]) -> float:
        return math.sqrt(sum(value * value for value in vector.values()))

    def best_match(self, question: str) -> tuple[AnalysisSkill | None, float]:
        query = self._tf(_tokenize(question))
        if not query:
            return None, 0.0
        best: AnalysisSkill | None = None
        best_score = 0.0
        for index, skill in enumerate(self.skills):
            score = 0.0
            for term, qtf in query.items():
                if term in self.vectors[index]:
                    score += qtf * self.idf.get(term, 0.0) * self.vectors[index][term]
            qnorm = math.sqrt(sum(qtf * qtf * self.idf.get(term, 0.0) ** 2 for term, qtf in query.items()))
            denominator = self.norms[index] * qnorm
            similarity = score / denominator if denominator > 0 else 0.0
            if similarity > best_score:
                best, best_score = skill, similarity
        return best, best_score
