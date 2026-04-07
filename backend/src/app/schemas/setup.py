from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SellerSourceStatusLiteral = Annotated[str, Field(pattern="^(manual|imported|generated)$")]
ICPStatusLiteral = Annotated[str, Field(pattern="^(draft|active|archived)$")]


class SellerProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    company_name: str = Field(min_length=1, max_length=255)
    company_domain: str | None = Field(default=None, max_length=255)
    product_summary: str = Field(min_length=1)
    value_proposition: str = Field(min_length=1)
    target_market_summary: str | None = None
    source_status: SellerSourceStatusLiteral | None = None
    profile_json: dict[str, Any] | None = None


class SellerProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    company_domain: str | None = Field(default=None, max_length=255)
    product_summary: str | None = Field(default=None, min_length=1)
    value_proposition: str | None = Field(default=None, min_length=1)
    target_market_summary: str | None = None
    source_status: SellerSourceStatusLiteral | None = None
    profile_json: dict[str, Any] | None = None


class SellerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seller_profile_id: UUID
    tenant_id: UUID
    created_by_user_id: UUID
    updated_by_user_id: UUID | None
    name: str
    company_name: str
    company_domain: str | None
    product_summary: str
    value_proposition: str
    target_market_summary: str | None
    source_status: str | None
    profile_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class SellerProfileListResponse(BaseModel):
    items: list[SellerProfileResponse]
    total: int
    limit: int
    offset: int


class ICPProfileCreateRequest(BaseModel):
    seller_profile_id: UUID
    name: str = Field(min_length=1, max_length=255)
    status: ICPStatusLiteral | None = None
    criteria_json: dict[str, Any]
    exclusions_json: dict[str, Any] | None = None


class ICPProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: ICPStatusLiteral | None = None
    criteria_json: dict[str, Any] | None = None
    exclusions_json: dict[str, Any] | None = None


class ICPProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    icp_profile_id: UUID
    tenant_id: UUID
    seller_profile_id: UUID
    created_by_user_id: UUID
    updated_by_user_id: UUID | None
    name: str
    status: str
    criteria_json: dict[str, Any]
    exclusions_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ICPProfileListResponse(BaseModel):
    items: list[ICPProfileResponse]
    total: int
    limit: int
    offset: int
