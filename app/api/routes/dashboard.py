from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.repositories.catalog import list_interfaces
from app.services.query_gateway import QueryGateway


router = APIRouter(tags=["dashboard"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("/health")
def health(conn: Db) -> dict:
    conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "database": "ready", "agent": "langgraph"}


@router.get("/dashboard")
def dashboard(conn: Db, year: int = Query(2026, ge=2000, le=2100)) -> dict:
    gateway = QueryGateway(conn)
    params = gateway.approve("biz.dashboard.summary", {"year": year})
    return gateway.execute("biz.dashboard.summary", params)


@router.get("/bootstrap")
def bootstrap(conn: Db) -> dict:
    return {
        "interfaces": list_interfaces(conn, status="启用"),
        "units": [x[0] for x in conn.execute("SELECT unit_name FROM dim_org_unit WHERE enabled=1 ORDER BY id")],
        "industries": [x[0] for x in conn.execute("SELECT industry_name FROM dim_industry WHERE enabled=1 ORDER BY id")],
        "productLines": [x[0] for x in conn.execute("SELECT line_name FROM dim_product_line WHERE enabled=1 ORDER BY id")],
    }
