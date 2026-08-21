from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Generator

from app.core.config import settings
from app.repositories.catalog import ensure_interface_approval_policy
from app.repositories.runs import ensure_run_table
from app.repositories.skills import seed_default_skills


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.database_path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def initialize_database() -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    if not settings.database_path.exists() and settings.seed_database_path.exists():
        shutil.copy2(settings.seed_database_path, settings.database_path)
    conn = connect()
    try:
        has_schema = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='qa_session'"
        ).fetchone()
        if not has_schema:
            conn.executescript(settings.schema_path.read_text(encoding="utf-8"))
        app_config_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(app_config)").fetchall()
        }
        if "greeting_enabled" not in app_config_columns:
            conn.execute("ALTER TABLE app_config ADD COLUMN greeting_enabled INTEGER NOT NULL DEFAULT 1")
        if "frequent_threshold" not in app_config_columns:
            conn.execute("ALTER TABLE app_config ADD COLUMN frequent_threshold INTEGER NOT NULL DEFAULT 3")
        ensure_interface_approval_policy(conn)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS agent_skill (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 skill_code TEXT NOT NULL UNIQUE,
                 skill_name TEXT NOT NULL,
                 description TEXT,
                 trigger_keywords TEXT,
                 steps_json TEXT NOT NULL,
                 derived_metrics_json TEXT,
                 answer_sections_json TEXT,
                 status TEXT NOT NULL DEFAULT '启用',
                 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_skill_status ON agent_skill (status)")
        seed_default_skills(conn, seed_when_empty=True)
        ensure_run_table(conn)
        conn.execute(
            """INSERT OR IGNORE INTO llm_config(id, provider, base_url, model_name, api_key)
               VALUES(1, 'openai', 'https://api.openai.com/v1', 'gpt-5-mini', '')"""
        )
        conn.execute(
            """INSERT OR IGNORE INTO app_config(
                   id, greeting_enabled, opening_greeting, opening_questions,
                   next_suggestions_enabled, next_suggestions_count, frequent_enabled,
                   frequent_threshold
               ) VALUES(1, 1, ?, ?, 1, 3, 1, 3)""",
            (
                "欢迎使用智能AI问数，您可以向我咨询经营数据、报表分析相关问题。",
                '["今年各经营单元收入完成情况如何？","哪些行业同比增长最快？","当前高风险商机有哪些？"]',
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
