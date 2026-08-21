from __future__ import annotations

import sqlite3
from typing import Any

from app.core.errors import BusinessError
from app.repositories.common import dumps, loads


MODEL_PROVIDERS = {
    "openai": {"label": "OpenAI", "baseUrl": "https://api.openai.com/v1", "models": ["gpt-5-mini", "gpt-5", "gpt-4.1-mini"]},
    "deepseek": {"label": "DeepSeek V4", "baseUrl": "https://api.deepseek.com", "models": ["deepseek-v4-pro", "deepseek-v4-flash"]},
}


def mask_key(value: str) -> str:
    if not value:
        return ""
    return "***" if len(value) <= 12 else f"{value[:6]}...{value[-4:]}"


def get_llm_config(conn: sqlite3.Connection, reveal: bool = False) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM llm_config WHERE id=1").fetchone()
    if not row:
        raise BusinessError("MODEL_CONFIG_MISSING", "模型配置不存在", 500)
    provider = row["provider"] if row["provider"] in MODEL_PROVIDERS else "openai"
    key = row["api_key"] or ""
    return {
        "provider": provider,
        "baseUrl": row["base_url"],
        "modelName": row["model_name"],
        "apiKey": key if reveal else mask_key(key),
        "hasApiKey": bool(key),
        "streamEnabled": bool(row["stream_enabled"]),
        "temperature": row["temperature"],
        "maxOutputTokens": row["max_output_tokens"],
        "updatedAt": row["updated_at"],
        "providerOptions": MODEL_PROVIDERS,
    }


def update_llm_config(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_llm_config(conn, reveal=True)
    provider = str(payload.get("provider") or current["provider"]).lower()
    if provider not in MODEL_PROVIDERS:
        raise BusinessError("VALIDATION_ERROR", "Provider 只支持 openai 或 deepseek")
    meta = MODEL_PROVIDERS[provider]
    submitted_key = str(payload.get("apiKey") or "")
    api_key = current["apiKey"] if not submitted_key or "..." in submitted_key or submitted_key == "***" else submitted_key
    conn.execute(
        """UPDATE llm_config SET provider=?, base_url=?, model_name=?, api_key=?, stream_enabled=?,
           temperature=?, max_output_tokens=?, updated_at=CURRENT_TIMESTAMP WHERE id=1""",
        (provider, payload.get("baseUrl") or meta["baseUrl"], payload.get("modelName") or meta["models"][0],
         api_key, int(bool(payload.get("streamEnabled", True))), float(payload.get("temperature", .2)),
         max(256, min(int(payload.get("maxOutputTokens", 2048)), 16384))),
    )
    return get_llm_config(conn)


def frequent_questions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM qa_frequent_question ORDER BY hit_count DESC, last_asked_at DESC LIMIT 20").fetchall()
    return [{"id": row["id"], "question": row["question"], "hitCount": row["hit_count"], "lastAskedAt": row["last_asked_at"]} for row in rows]


def get_app_config(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM app_config WHERE id=1").fetchone()
    return {
        "greetingEnabled": bool(row["greeting_enabled"]),
        "openingGreeting": row["opening_greeting"] or "欢迎使用智能问数。",
        "openingQuestions": loads(row["opening_questions"], []),
        "nextSuggestionsEnabled": bool(row["next_suggestions_enabled"]),
        "nextSuggestionsCount": max(1, min(int(row["next_suggestions_count"] or 3), 6)),
        "frequentEnabled": bool(row["frequent_enabled"]),
        "frequentThreshold": max(1, min(int(row["frequent_threshold"] or 3), 20)),
        "frequentQuestions": frequent_questions(conn),
        "updatedAt": row["updated_at"],
    }


def update_app_config(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_app_config(conn)
    questions = payload.get("openingQuestions", current["openingQuestions"])
    questions = [str(item).strip()[:120] for item in questions if str(item).strip()][:10]
    conn.execute(
        """UPDATE app_config SET greeting_enabled=?, opening_greeting=?, opening_questions=?,
           next_suggestions_enabled=?, next_suggestions_count=?, frequent_enabled=?,
           frequent_threshold=?, updated_at=CURRENT_TIMESTAMP WHERE id=1""",
        (int(bool(payload.get("greetingEnabled", current["greetingEnabled"]))),
         str(payload.get("openingGreeting", current["openingGreeting"])).strip()[:240], dumps(questions),
         int(bool(payload.get("nextSuggestionsEnabled", current["nextSuggestionsEnabled"]))),
         max(1, min(int(payload.get("nextSuggestionsCount", current["nextSuggestionsCount"])), 6)),
         int(bool(payload.get("frequentEnabled", current["frequentEnabled"]))),
         max(1, min(int(payload.get("frequentThreshold", current["frequentThreshold"])), 20))),
    )
    return get_app_config(conn)
