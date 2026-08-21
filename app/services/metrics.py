from __future__ import annotations

from typing import Any


def compute_derived_metrics(matched_skill: dict[str, Any] | None, results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"items": [], "tables": []}
    by_code = {item.get("interfaceCode"): item for item in results}
    items: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []

    unit_rows = list((by_code.get("biz.unitAchievement.query") or {}).get("rows") or [])
    if unit_rows:
        total_target = _sum(unit_rows, "targetAmount")
        total_income = _sum(unit_rows, "incomeAmount")
        gap = round(total_target - total_income, 2)
        items.extend([
            {"name": "totalTargetAmount", "label": "目标金额", "value": round(total_target, 2), "unit": "万元"},
            {"name": "totalIncomeAmount", "label": "收入金额", "value": round(total_income, 2), "unit": "万元"},
            {"name": "gapAmount", "label": "目标缺口", "value": gap, "unit": "万元"},
            {"name": "completionRate", "label": "整体完成率", "value": round(total_income / total_target * 100, 2) if total_target else 0, "unit": "%"},
        ])
        gap_rows = []
        for row in unit_rows:
            target = _number(row.get("targetAmount"))
            income = _number(row.get("incomeAmount"))
            gap_value = round(target - income, 2)
            if gap_value > 0:
                gap_rows.append({"unitName": row.get("orgUnitName"), "targetAmount": target, "incomeAmount": income, "gapAmount": gap_value})
        gap_rows.sort(key=lambda row: row["gapAmount"], reverse=True)
        if gap_rows:
            tables.append({"name": "underAchievedUnits", "label": "未达成经营单元", "rows": gap_rows[:10]})

    risk_rows = list((by_code.get("ledger.pplRisk.summary") or {}).get("rows") or [])
    if risk_rows:
        risk_amount = round(_sum(risk_rows, "amount"), 2)
        risk_count = sum(int(_number(row.get("projectCount"))) for row in risk_rows)
        items.extend([
            {"name": "riskExposureAmount", "label": "风险敞口金额", "value": risk_amount, "unit": "万元"},
            {"name": "riskProjectCount", "label": "风险商机数", "value": risk_count, "unit": "个"},
        ])
        total_income = _metric_value(items, "totalIncomeAmount")
        if total_income:
            items.append({"name": "riskToIncomeRatio", "label": "风险收入比", "value": round(risk_amount / total_income * 100, 2), "unit": "%"})

    product_rows = list((by_code.get("biz.productLine.analysis") or {}).get("rows") or [])
    if product_rows:
        total_product_amount = _sum(product_rows, "amount")
        if total_product_amount:
            top = max(product_rows, key=lambda row: _number(row.get("amount")))
            items.append({
                "name": "topProductContribution",
                "label": "最高产品线贡献占比",
                "value": round(_number(top.get("amount")) / total_product_amount * 100, 2),
                "unit": "%",
                "dimension": top.get("productLine"),
            })

    return {
        "skillCode": (matched_skill or {}).get("code"),
        "skillName": (matched_skill or {}).get("name"),
        "items": _dedupe_items(items),
        "tables": tables,
    }


def _sum(rows: list[dict[str, Any]], field: str) -> float:
    return sum(_number(row.get(field)) for row in rows)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _metric_value(items: list[dict[str, Any]], name: str) -> float:
    item = next((metric for metric in items if metric.get("name") == name), None)
    return _number(item.get("value")) if item else 0


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        name = str(item.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(item)
    return result
