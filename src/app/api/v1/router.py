from fastapi import APIRouter

from app.api.v1.endpoints.agents import router as agents_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.identity import router as identity_router
from app.api.v1.endpoints.tenancy import router as tenancy_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(agents_router, prefix="/agents", tags=["agents"])
api_router.include_router(identity_router, tags=["identity"])
api_router.include_router(tenancy_router, tags=["tenancy"])
