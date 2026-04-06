from __future__ import annotations

from pydantic import BaseModel


class MeResponse(BaseModel):
    user_id: str
    external_auth_subject: str
    email: str | None = None
    display_name: str | None = None
    is_platform_admin: bool = False
    request_id: str


class TenantSummary(BaseModel):
    tenant_id: str
    tenant_name: str
    role: str
    status: str


class TenantListResponse(BaseModel):
    tenants: list[TenantSummary]
