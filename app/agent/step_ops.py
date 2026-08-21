from __future__ import annotations

from collections import defaultdict
from typing import Any


def resolve_params(call: dict[str, Any], state: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    params = {key: _resolve_value(value, state, step_outputs) for key, value in dict(call.get("params") or {}).items()}
    for name, source in dict(call.get("paramSources") or {}).items():
        value = resolve_source(source, state, step_outputs)
        if value not in (None, "", []):
            params[name] = value
    return {key: value for key, value in params.items() if value not in (None, "", [])}


def resolve_source(source: Any, state: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> Any:
    if isinstance(source, str):
        return _resolve_value(source, state, step_outputs)
    if not isinstance(source, dict):
        return source
    value = None
    from_step = str(source.get("fromStep") or "")
    if from_step:
        value = read_path(step_outputs.get(from_step, {}), str(source.get("path") or "rows"))
    elif source.get("value") is not None:
        value = _resolve_value(source.get("value"), state, step_outputs)
    if value in (None, "", []) and source.get("fallback") is not None:
        value = _resolve_value(source.get("fallback"), state, step_outputs)
    if isinstance(value, list):
        if source.get("unique", True):
            value = _unique(value)
        limit = _int(source.get("limit"), 0)
        if limit > 0:
            value = value[:limit]
    return value


def apply_transform(step_id: str, transform: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    operation = str(transform.get("operation") or transform.get("type") or "").strip()
    if operation == "selectDistinct":
        rows = _select_distinct(transform, step_outputs)
    elif operation == "top":
        rows = _top(transform, step_outputs)
    elif operation == "filterRows":
        rows = _filter_rows(transform, step_outputs)
    elif operation == "computeGap":
        rows = _compute_gap(transform, step_outputs)
    elif operation == "aggregate":
        rows = _aggregate(transform, step_outputs)
    else:
        raise ValueError(f"不支持的 Skill 派生操作：{operation or '空'}")
    return {
        "stepId": step_id,
        "interfaceCode": f"skill.derive.{step_id}",
        "columns": _infer_columns(rows),
        "rows": rows,
        "summary": {"rowCount": len(rows), "operation": operation},
        "trace": {"durationMs": 0, "rowCount": len(rows), "derived": True},
    }


def read_path(source: Any, path: str) -> Any:
    current = source
    for part in [item for item in path.split(".") if item]:
        if part.endswith("[]"):
            key = part[:-2]
            if isinstance(current, dict):
                current = current.get(key, [])
            if not isinstance(current, list):
                return []
            continue
        if isinstance(current, list):
            current = [_get_value(item, part) for item in current]
            current = [item for item in current if item not in (None, "")]
        else:
            current = _get_value(current, part)
    return current


def _resolve_value(value: Any, state: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, str):
        if value.startswith("$steps."):
            pieces = value[len("$steps."):].split(".", 1)
            if len(pieces) != 2:
                return None
            return read_path(step_outputs.get(pieces[0], {}), pieces[1])
        if value.startswith("$entities."):
            return read_path(state.get("entities", {}), value[len("$entities."):])
    if isinstance(value, list):
        return [_resolve_value(item, state, step_outputs) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_value(item, state, step_outputs) for key, item in value.items()}
    return value


def _select_distinct(transform: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _source_rows(transform, step_outputs)
    field = str(transform.get("field") or "")
    output = str(transform.get("as") or field or "value")
    values = _unique([row.get(field) for row in rows if isinstance(row, dict)])
    limit = _int(transform.get("limit"), len(values))
    return [{output: value} for value in values[:limit]]


def _top(transform: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in _source_rows(transform, step_outputs) if isinstance(row, dict)]
    by = str(transform.get("by") or "")
    reverse = str(transform.get("order") or "desc").lower() != "asc"
    rows.sort(key=lambda row: _number(row.get(by)), reverse=reverse)
    return rows[:_int(transform.get("limit"), 10)]


def _filter_rows(transform: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in _source_rows(transform, step_outputs) if isinstance(row, dict)]
    where = transform.get("where") if isinstance(transform.get("where"), dict) else {}
    field = str(where.get("field") or "")
    op = str(where.get("op") or "eq")
    expected = where.get("value")
    filtered = [row for row in rows if _match(row.get(field), op, expected)]
    return filtered[:_int(transform.get("limit"), len(filtered))]


def _compute_gap(transform: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    target_field = str(transform.get("targetField") or "targetAmount")
    actual_field = str(transform.get("actualField") or "incomeAmount")
    output_field = str(transform.get("outputField") or "gapAmount")
    dimension_fields = transform.get("dimensionFields") if isinstance(transform.get("dimensionFields"), list) else []
    rows = []
    for row in _source_rows(transform, step_outputs):
        if not isinstance(row, dict):
            continue
        gap = round(_number(row.get(target_field)) - _number(row.get(actual_field)), 2)
        if transform.get("positiveOnly") and gap <= 0:
            continue
        kept = {field: row.get(field) for field in dimension_fields if field in row}
        kept.update({target_field: row.get(target_field), actual_field: row.get(actual_field), output_field: gap})
        rows.append(kept)
    sort_by = str(transform.get("sortBy") or output_field)
    reverse = str(transform.get("order") or "desc").lower() != "asc"
    rows.sort(key=lambda row: _number(row.get(sort_by)), reverse=reverse)
    return rows[:_int(transform.get("limit"), len(rows))]


def _aggregate(transform: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [row for row in _source_rows(transform, step_outputs) if isinstance(row, dict)]
    group_by = [str(item) for item in transform.get("groupBy", [])] if isinstance(transform.get("groupBy"), list) else []
    metrics = transform.get("metrics") if isinstance(transform.get("metrics"), list) else []
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(field) for field in group_by)].append(row)
    output = []
    for key, items in groups.items():
        row = {field: value for field, value in zip(group_by, key)}
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            field = str(metric.get("field") or "")
            op = str(metric.get("op") or "sum")
            name = str(metric.get("as") or f"{op}_{field or 'rows'}")
            values = [_number(item.get(field)) for item in items] if field else []
            if op == "count":
                row[name] = len(items)
            elif op == "avg":
                row[name] = round(sum(values) / len(values), 2) if values else 0
            elif op == "min":
                row[name] = round(min(values), 2) if values else 0
            elif op == "max":
                row[name] = round(max(values), 2) if values else 0
            else:
                row[name] = round(sum(values), 2)
        output.append(row)
    return output[:_int(transform.get("limit"), len(output))]


def _source_rows(transform: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> list[Any]:
    return list(read_path(step_outputs.get(str(transform.get("fromStep") or ""), {}), str(transform.get("path") or "rows")) or [])


def _infer_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    return [{"field": field, "label": field, "type": "number" if any(isinstance(row.get(field), (int, float)) for row in rows) else "string", "unit": ""} for field in fields]


def _get_value(source: Any, part: str) -> Any:
    if isinstance(source, dict):
        return source.get(part)
    return None


def _match(value: Any, op: str, expected: Any) -> bool:
    if op == "gt":
        return _number(value) > _number(expected)
    if op == "gte":
        return _number(value) >= _number(expected)
    if op == "lt":
        return _number(value) < _number(expected)
    if op == "lte":
        return _number(value) <= _number(expected)
    if op == "ne":
        return value != expected
    if op == "in":
        return value in expected if isinstance(expected, list) else False
    if op == "contains":
        return str(expected) in str(value)
    return value == expected


def _unique(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    output = []
    for value in values:
        if value in (None, ""):
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
