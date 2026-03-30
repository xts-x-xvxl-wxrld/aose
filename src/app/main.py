from fastapi import FastAPI

from app.api.v1.router import api_router
from app.agents.registry import build_agent_system
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.state.agent_system = build_agent_system(settings)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
