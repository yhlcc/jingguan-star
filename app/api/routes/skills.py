from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from app.core.database import get_db
from app.repositories.skills import delete_skill, get_skill, import_skills, list_skills, save_skill, set_skill_status


router = APIRouter(tags=["skills"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("/agent-skills")
def skills(conn: Db, keyword: str | None = None, status: str | None = None) -> dict:
    return {"items": list_skills(conn, keyword, status)}


@router.post("/agent-skills")
def create(conn: Db, payload: dict[str, Any] = Body(...)) -> dict:
    return save_skill(conn, str(payload.get("skillCode", "")).strip(), payload, create=True)


@router.post("/agent-skills/import")
def import_skill_payload(conn: Db, payload: dict[str, Any] = Body(...)) -> dict:
    return import_skills(conn, payload)


@router.get("/agent-skills/{code}")
def detail(code: str, conn: Db) -> dict:
    return get_skill(conn, code)


@router.put("/agent-skills/{code}")
@router.patch("/agent-skills/{code}")
def update(code: str, conn: Db, payload: dict[str, Any] = Body(...)) -> dict:
    return save_skill(conn, code, payload)


@router.patch("/agent-skills/{code}/status")
def toggle(code: str, conn: Db, payload: dict[str, Any] = Body(...)) -> dict:
    return set_skill_status(conn, code, str(payload.get("status")))


@router.delete("/agent-skills/{code}")
def remove(code: str, conn: Db) -> dict:
    return delete_skill(conn, code)
