from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from app.core.database import get_db
from app.repositories.settings import frequent_questions, get_app_config, get_llm_config, update_app_config, update_llm_config


router = APIRouter(tags=["settings"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("/llm-config")
def llm_config(conn: Db) -> dict: return get_llm_config(conn)


@router.put("/llm-config")
def save_llm(conn: Db, payload: dict[str, Any] = Body(...)) -> dict: return update_llm_config(conn, payload)


@router.get("/app-config")
def app_config(conn: Db) -> dict: return get_app_config(conn)


@router.put("/app-config")
def save_app(conn: Db, payload: dict[str, Any] = Body(...)) -> dict: return update_app_config(conn, payload)


@router.get("/qa/frequent-questions")
def frequent(conn: Db) -> dict: return {"items": frequent_questions(conn)}
