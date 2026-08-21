from __future__ import annotations

from typing import Any


def build_answer_payload(results: list[dict[str, Any]], model_output: dict[str, Any], suggestions_count: int, matched_skill: dict[str, Any] | None = None, derived_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    primary = next((item for item in results if item.get("rows")), results[0] if results else {})
    rows = primary.get("rows", [])[:20]
    columns = primary.get("columns", [])
    findings = model_output.get("dataFindings") if isinstance(model_output.get("dataFindings"), list) else []
    if not findings:
        findings = deterministic_findings(results)
    suggestions = model_output.get("nextSuggestions") if isinstance(model_output.get("nextSuggestions"), list) else []
    visualization = build_visualization(columns, rows, model_output.get("visualization"))
    numeric = []
    for column in columns:
        values = [float(row[column["field"]]) for row in rows if isinstance(row.get(column["field"]), (int, float)) and not isinstance(row.get(column["field"]), bool)]
        if values:
            numeric.append({"field": column["field"], "label": column.get("label", column["field"]), "unit": column.get("unit", ""), "sum": round(sum(values), 2), "avg": round(sum(values)/len(values), 2), "max": round(max(values), 2), "min": round(min(values), 2)})
    return {
        "type": "structuredAnswer", "version": 2, "dataFound": bool(rows),
        "dataFindings": [str(x) for x in findings[:6]],
        "table": {"columns": columns, "rows": rows, "totalRows": len(primary.get("rows", []))},
        "resultSets": [
            {
                "stepId": item.get("stepId"),
                "interfaceCode": item.get("interfaceCode"),
                "purpose": item.get("purpose"),
                "columns": item.get("columns", []),
                "rows": list(item.get("rows", []))[:20],
                "totalRows": len(item.get("rows", [])),
                "summary": item.get("summary", {}),
            }
            for item in results
        ],
        "stats": {"rowCount": len(rows), "numeric": numeric[:4], "derived": (derived_metrics or {}).get("items", [])}, "visualization": visualization,
        "nextSuggestions": [str(x).strip() for x in suggestions if str(x).strip()][:suggestions_count],
        "source": {"interfaces": [{"stepId": x.get("stepId"), "interfaceCode": x.get("interfaceCode"), "requestId": x.get("requestId"), "rowCount": len(x.get("rows", [])), "dataAsOf": x.get("dataAsOf")} for x in results], "primaryInterfaceCode": primary.get("interfaceCode"), "matchedSkill": matched_skill},
        "derivedMetrics": derived_metrics or {"items": [], "tables": []},
    }


def deterministic_findings(results: list[dict[str, Any]]) -> list[str]:
    if not results: return ["本次没有获得可验证的数据结果。"]
    findings = []
    for item in results:
        findings.append(f"接口 {item.get('interfaceCode')} 返回 {len(item.get('rows', []))} 行已校验数据。")
    return findings


def build_visualization(columns: list[dict[str, Any]], rows: list[dict[str, Any]], plan: Any) -> dict[str, Any]:
    if not rows or not columns: return {"mode": "single", "chartType": "bar", "title": "暂无可视化数据", "data": []}
    label = next((x for x in columns if any(isinstance(row.get(x["field"]), str) for row in rows)), columns[0])
    numbers = [x for x in columns if any(isinstance(row.get(x["field"]), (int, float)) and not isinstance(row.get(x["field"]), bool) for row in rows)]
    if not numbers: return {"mode": "single", "chartType": "bar", "title": "数据分布", "data": []}
    requested = plan if isinstance(plan, dict) else {}
    fields = requested.get("metrics") if isinstance(requested.get("metrics"), list) else []
    metrics = [x for x in numbers if x["field"] in fields] or numbers[:min(3, len(numbers))]
    if len(metrics) == 1:
        metric = metrics[0]
        return {"mode": "single", "chartType": requested.get("chartType", "bar"), "title": requested.get("title") or f"{metric.get('label')}分析", "unit": metric.get("unit", ""),
                "data": [{"label": str(row.get(label["field"], "")), "value": row.get(metric["field"], 0)} for row in rows[:12]]}
    units: list[str] = []
    for metric in metrics:
        if metric.get("unit", "") not in units: units.append(metric.get("unit", ""))
    return {"mode": "combined", "chartType": "combo", "title": requested.get("title") or "多指标组合分析",
            "series": [{"name": metric.get("label", metric["field"]), "chartType": "line" if metric.get("unit") == "%" else "bar", "unit": metric.get("unit", ""), "axisIndex": units.index(metric.get("unit", "")),
                        "data": [{"label": str(row.get(label["field"], "")), "value": row.get(metric["field"], 0)} for row in rows[:12]]} for metric in metrics]}


def answer_markdown(payload: dict[str, Any]) -> str:
    findings = "\n".join(f"- {item}" for item in payload.get("dataFindings", []))
    sources = payload.get("source", {}).get("interfaces", [])
    source_text = "、".join(str(item.get("interfaceCode")) for item in sources) or "无"
    return f"## 数据发现\n{findings}\n\n## 数据表格\n已按通过校验的数据渲染结果表格。\n\n## 数据统计结果总结\n- 返回行数：{payload.get('stats', {}).get('rowCount', 0)}\n- 数据接口：{source_text}\n\n## 数据可视化\n已根据指标量纲生成图表。"
