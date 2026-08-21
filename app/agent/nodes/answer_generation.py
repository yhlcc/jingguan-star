from __future__ import annotations

from app.agent.cancel import ensure_not_cancelled
from app.agent.context import AgentContext
from app.agent.state import AgentState
from app.services.answer import answer_markdown, build_answer_payload
from app.services.llm import extract_json_string_field


def answer_generation(context: AgentContext, state: AgentState) -> dict:
    ensure_not_cancelled(context)
    if state.get("intent") == "direct_chat":
        return _direct_answer(context, state)
    return _business_answer(context, state)


def _direct_answer(context: AgentContext, state: AgentState) -> dict:
    buffer = {"text": ""}
    emitted = {"value": 0}

    def on_delta(delta: str) -> None:
        ensure_not_cancelled(context)
        buffer["text"] += delta
        prefix = extract_json_string_field(buffer["text"], "answer")
        new = prefix[emitted["value"]:]
        if new:
            context.emit("delta", {"content": new})
            emitted["value"] += len(new)

    output = context.llm.stream_json(
        "你是经管之星智能经营助手。自然简短回应，不得编造经营数据，只返回 JSON。",
        {"question": state["question"], "conversationHistory": state.get("history", []),
         "outputSchema": {"answer": "回复", "nextSuggestions": ["可继续询问的问题"]},
         "nextSuggestionsCount": context.next_suggestions_count},
        on_delta=on_delta,
    )
    answer = str(output.get("answer") or "我可以帮你分析经营概览、收入排名、行业表现、产品结构和商机风险。")
    if not emitted["value"]:
        context.emit("delta", {"content": answer})
    payload = {"type": "directAnswer", "nextSuggestions": list(output.get("nextSuggestions") or [])[:context.next_suggestions_count]}
    return {"final_answer": answer, "answer_payload": payload}


def _business_answer(context: AgentContext, state: AgentState) -> dict:
    ensure_not_cancelled(context)
    results = state.get("validated_results", [])
    output = context.llm.json(
        "你是经营数据分析助手。只能基于通过校验的数据总结，不得补造数值。只返回 JSON。",
        {"question": state["question"], "conversationHistory": state.get("history", []),
         "validatedResults": [{"interfaceCode": x.get("interfaceCode"), "purpose": x.get("purpose"), "columns": x.get("columns", []), "rows": x.get("rows", [])[:20], "summary": x.get("summary", {})} for x in results],
         "matchedSkill": state.get("matched_skill"),
         "derivedMetrics": state.get("derived_metrics", {}),
         "executionErrors": state.get("execution_errors", []), "validationReport": state.get("validation_report", {}),
         "outputSchema": {"dataFindings": ["跨接口经营发现"], "visualization": {"chartType": "bar|line|pie", "title": "标题", "metrics": ["字段名"]}, "nextSuggestions": ["建议追问"]},
         "nextSuggestionsCount": context.next_suggestions_count},
    )
    payload = build_answer_payload(results, output, context.next_suggestions_count, state.get("matched_skill"), state.get("derived_metrics", {}))
    fallback = answer_markdown(payload)
    return {"final_answer": fallback, "answer_payload": payload}
