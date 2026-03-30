from uuid import uuid4

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.agents.registry import build_agent_system
from app.api.v1.router import api_router
from app.config import get_settings
from app.schemas.errors import ErrorResponse
from app.services.errors import ServiceError


async def handle_service_error(_request: Request, exc: ServiceError) -> JSONResponse:
    payload = ErrorResponse(
        error_code=exc.error_code,
        message=exc.message,
        request_id=_request.headers.get("X-Request-ID") or str(uuid4()),
        details=exc.details,
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump(mode="json"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.state.agent_system = build_agent_system(settings)
    app.add_exception_handler(ServiceError, handle_service_error)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
