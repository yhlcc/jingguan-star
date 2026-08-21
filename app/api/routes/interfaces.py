from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query

from app.core.database import get_db
from app.repositories.audits import write_audit
from app.repositories.catalog import get_interface, list_interfaces, save_interface, set_interface_status
from app.services.query_gateway import QueryGateway


router = APIRouter(tags=["interfaces"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("/query-interfaces")
def interfaces(conn: Db, keyword: str | None = None, status: str | None = None, groupName: str | None = None) -> dict:
    return {"items": list_interfaces(conn, keyword, status, groupName)}


@router.post("/query-interfaces")
def create(conn: Db, payload: dict[str, Any] = Body(...)) -> dict:
    return save_interface(conn, str(payload.get("interfaceCode", "")).strip(), payload, create=True)


@router.get("/query-interfaces/{code}")
def detail(code: str, conn: Db) -> dict:
    return get_interface(conn, code)


@router.put("/query-interfaces/{code}")
@router.patch("/query-interfaces/{code}")
def update(code: str, conn: Db, payload: dict[str, Any] = Body(...)) -> dict:
    return save_interface(conn, code, payload)


@router.patch("/query-interfaces/{code}/status")
def toggle(code: str, conn: Db, payload: dict[str, Any] = Body(...)) -> dict:
    return set_interface_status(conn, code, str(payload.get("status")))


@router.post("/ai-query/{code}")
def execute(code: str, conn: Db, payload: dict[str, Any] = Body(default_factory=dict)) -> dict:
    gateway = QueryGateway(conn)
    params = gateway.approve(code, payload)
    result = gateway.execute(code, params)
    write_audit(conn, request_id=result["requestId"], session_id=params.get("sessionId"), interface_code=code, params=params, row_count=len(result.get("rows", [])), duration_ms=result["trace"]["durationMs"], status="成功")
    return result


@router.get("/ledgers/commercial")
def commercial(conn: Db, year: int = 2026, pageSize: int = Query(50, ge=1, le=100)) -> dict:
    gateway = QueryGateway(conn); params = gateway.approve("ledger.commercial.detail", {"year": year, "pageSize": pageSize}); return gateway.execute("ledger.commercial.detail", params)


@router.get("/ledgers/ppl")
def ppl(conn: Db, pageSize: int = Query(50, ge=1, le=100)) -> dict:
    gateway = QueryGateway(conn); params = gateway.approve("ledger.ppl.detail", {"pageSize": pageSize}); return gateway.execute("ledger.ppl.detail", params)


@router.get("/ledgers/goals")
def goals(conn: Db, year: int = 2026, pageSize: int = Query(50, ge=1, le=100)) -> dict:
    gateway = QueryGateway(conn); params = gateway.approve("ledger.goal.query", {"year": year, "pageSize": pageSize}); return gateway.execute("ledger.goal.query", params)
