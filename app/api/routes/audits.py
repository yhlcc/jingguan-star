from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.repositories.audits import get_audit, list_audits


router = APIRouter(tags=["audits"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("/audits")
def audits(conn: Db, pageSize: int = Query(50, ge=1, le=100)) -> dict: return {"items": list_audits(conn, pageSize)}


@router.get("/audits/{audit_id}")
def audit(audit_id: int, conn: Db) -> dict: return get_audit(conn, audit_id)
