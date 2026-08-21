from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    database_path: Path = Path(os.getenv("DATABASE_PATH", ROOT / "data" / "jingguan_star.db"))
    schema_path: Path = ROOT / "db_schema.sql"
    frontend_dist: Path = ROOT / "frontend" / "dist"
    seed_database_path: Path = Path(os.getenv("SEED_DATABASE_PATH", ROOT / "seed" / "jingguan_star.db"))
    cors_origins: tuple[str, ...] = tuple(
        item.strip() for item in os.getenv(
            "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
        ).split(",") if item.strip()
    )
    serve_frontend: bool = os.getenv("SERVE_FRONTEND", "true").lower() == "true"
    model_timeout_seconds: float = float(os.getenv("AGENT_MODEL_TIMEOUT_SECONDS", "60"))
    model_max_retries: int = int(os.getenv("AGENT_MODEL_MAX_RETRIES", "2"))
    checkpointer: str = os.getenv("AGENT_CHECKPOINTER", "sqlite")
    checkpoint_path: Path = Path(os.getenv("AGENT_CHECKPOINT_PATH", ROOT / "data" / "agent_checkpoints.db"))
    skill_match: str = os.getenv("AGENT_SKILL_MATCH", "auto")
    skill_vector_threshold: float = float(os.getenv("AGENT_SKILL_VECTOR_THRESHOLD", "0.25"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
