from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.database import initialize_database
from app.core.errors import BusinessError
from app.core.logging import configure_logging


configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting application database_path=%s checkpoint_path=%s", settings.database_path, settings.checkpoint_path)
    initialize_database()
    logger.info("Application startup complete")
    yield
    logger.info("Application shutdown complete")


app = FastAPI(title="经管之星 API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(api_router)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000)
        logger.exception(
            "Unhandled request error request_id=%s method=%s path=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        return JSONResponse(
            {"error": {"code": "INTERNAL_SERVER_ERROR", "message": "服务端执行失败，请查看服务端日志。"}},
            status_code=500,
            headers={"X-Request-ID": request_id},
        )
    duration_ms = round((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    if request.url.path.startswith("/api"):
        logger.info(
            "HTTP request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
    return response


@app.exception_handler(BusinessError)
async def business_error(request: Request, exc: BusinessError) -> JSONResponse:
    logger.warning("Business error method=%s path=%s code=%s message=%s", request.method, request.url.path, exc.code, exc.message)
    return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("Validation error method=%s path=%s details=%s", request.method, request.url.path, exc.errors())
    return JSONResponse({"error": {"code": "VALIDATION_ERROR", "message": "请求参数校验失败", "details": exc.errors()}}, status_code=422)


if settings.serve_frontend and settings.frontend_dist.exists():
    assets = settings.frontend_dist / "assets"
    if assets.exists(): app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        target = settings.frontend_dist / full_path
        if target.is_file(): return FileResponse(target)
        return FileResponse(settings.frontend_dist / "index.html")
