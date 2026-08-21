from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from app.core.database import get_db
from app.repositories.feedback import create_feedback, get_feedback, list_feedback, update_feedback


router = APIRouter(tags=["feedback"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("/qa/feedback")
def feedback(conn: Db) -> dict: return {"items": list_feedback(conn)}


@router.post("/qa/feedback")
def create(conn: Db, payload: dict[str, Any] = Body(...)) -> dict: return create_feedback(conn, payload)


@router.get("/qa/feedback/{feedback_id}")
def detail(feedback_id: int, conn: Db) -> dict: return get_feedback(conn, feedback_id)


@router.patch("/qa/feedback/{feedback_id}")
def update(feedback_id: int, conn: Db, payload: dict[str, Any] = Body(...)) -> dict: return update_feedback(conn, feedback_id, payload)
