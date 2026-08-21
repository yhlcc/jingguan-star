from __future__ import annotations

from app.agent.context import AgentContext
from app.agent.state import AgentState
from app.repositories.catalog import allowed_fields
from app.services.metrics import compute_derived_metrics


def data_validation(context: AgentContext, state: AgentState) -> dict:
    validated, reports = [], []
    for result in state.get("execution_results", []):
        code = result["interfaceCode"]
        columns = _result_columns(context, code, result)
        allowed = {item["field"] for item in columns}
        rows = result.get("rows") if isinstance(result.get("rows"), list) else []
        clean_rows, removed, type_warnings = [], set(), []
        for row in rows[:100]:
            if not isinstance(row, dict): continue
            unknown = set(row) - allowed
            removed.update(unknown)
            clean_row = {key: value for key, value in row.items() if key in allowed}
            for column in columns:
                field = column["field"]
                if field in clean_row and not _matches_type(clean_row[field], str(column.get("type") or "")):
                    type_warnings.append({"field": field, "expected": column.get("type"), "value": clean_row[field]})
            clean_rows.append(clean_row)
        clean = {**result, "columns": columns, "rows": clean_rows}
        clean["trace"] = {**result.get("trace", {}), "rowCount": len(clean_rows), "validated": True}
        validated.append(clean)
        reports.append({
            "interfaceCode": code,
            "stepId": result.get("stepId"),
            "valid": True,
            "rowCount": len(clean_rows),
            "sourceRowCount": len(rows),
            "truncated": len(rows) > 100,
            "removedFields": sorted(removed),
            "typeWarnings": type_warnings[:20],
            "empty": not clean_rows,
        })
    derived = compute_derived_metrics(state.get("matched_skill"), validated)
    return {"validated_results": validated, "validation_report": {"valid": bool(validated) or state.get("intent") == "direct_chat", "interfaces": reports, "errors": state.get("execution_errors", [])}, "derived_metrics": derived}


def _result_columns(context: AgentContext, code: str, result: dict) -> list[dict]:
    if code.startswith("skill.derive."):
        columns = result.get("columns") if isinstance(result.get("columns"), list) else []
        if columns:
            return columns
        fields = []
        for row in result.get("rows", []):
            if not isinstance(row, dict):
                continue
            for field in row:
                if field not in fields:
                    fields.append(field)
        return [{"field": field, "label": field, "type": "string", "unit": ""} for field in fields]
    return allowed_fields(context.conn, code)


def _matches_type(value, expected: str) -> bool:
    if value is None or expected in ("", "any"):
        return True
    if expected in {"number", "numeric", "decimal", "float", "int"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected.endswith("[]"):
        return isinstance(value, list)
    return isinstance(value, (str, int, float, bool))
