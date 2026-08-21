from __future__ import annotations

import json
from typing import Any


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def as_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def clamp_page_size(value: Any) -> int:
    try:
        return max(1, min(int(value or 50), 100))
    except (TypeError, ValueError):
        return 50
