from fastapi import APIRouter

from app.api.routes import assistant, audits, dashboard, feedback, interfaces, settings, skills


api_router = APIRouter(prefix="/api")
for route in (dashboard.router, interfaces.router, skills.router, assistant.router, audits.router, feedback.router, settings.router):
    api_router.include_router(route)
