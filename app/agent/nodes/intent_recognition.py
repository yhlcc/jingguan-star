from __future__ import annotations

from app.agent.context import AgentContext
from app.agent.state import AgentState


DIRECT_WORDS = {"hi", "hello", "你好", "您好", "在吗", "谢谢", "你能做什么", "你是谁"}


def intent_recognition(context: AgentContext, state: AgentState) -> dict:
    question = state["question"].strip()
    if question.lower() in DIRECT_WORDS:
        return {"intent": "direct_chat", "entities": {}}
    result = context.llm.json(
        "你是经营管理问题意图识别器。只返回 JSON，不查询数据，不回答问题。",
        {"question": question, "conversationHistory": state.get("history", []),
         "outputSchema": {"intent": "business_query|direct_chat", "entities": {"year": 2026, "units": [], "industries": [], "products": []}},
         "rules": ["经营目标、收入、同比、行业、产品、台账、合同、回款、商机、风险均属于 business_query", "普通问候和能力介绍属于 direct_chat"]},
    )
    intent = "direct_chat" if result.get("intent") == "direct_chat" else "business_query"
    return {"intent": intent, "entities": result.get("entities") if isinstance(result.get("entities"), dict) else {}}
