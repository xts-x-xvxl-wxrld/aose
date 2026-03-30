from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RoleLiteral = Annotated[str, Field(pattern="^(owner|admin|member|reviewer)$")]
StatusLiteral = Annotated[str, Field(pattern="^(active|invited|disabled)$")]


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)


class TenantCreateResponse(BaseModel):
    tenant_id: UUID
    name: str
    slug: str
    creator_membership_id: UUID
    creator_role: str
    creator_status: str


class TenantMemberCreateRequest(BaseModel):
    user_id: UUID | None = None
    email: str | None = None
    role: RoleLiteral


class TenantMemberUpdateRequest(BaseModel):
    role: RoleLiteral | None = None
    status: StatusLiteral | None = None


class TenantOwnershipTransferRequest(BaseModel):
    target_membership_id: UUID
    rationale: str | None = Field(default=None, max_length=4000)


class TenantOwnershipTransferResponse(BaseModel):
    tenant_id: UUID
    previous_owner_membership_id: UUID
    new_owner_membership_id: UUID
    previous_owner_role: str
    new_owner_role: str


class TenantMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membership_id: UUID
    tenant_id: UUID
    user_id: UUID
    email: str | None
    display_name: str | None
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


class TenantMemberListResponse(BaseModel):
    members: list[TenantMemberResponse]
