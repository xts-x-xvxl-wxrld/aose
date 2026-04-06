from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypedDict


@dataclass(frozen=True)
class AuthIdentity:
    external_auth_subject: str
    email: str | None
    display_name: str | None


@dataclass(frozen=True)
class ResolvedUser:
    user_id: str
    external_auth_subject: str
    email: str | None
    display_name: str | None
    is_platform_admin: bool = False
    status: str = "active"


@dataclass(frozen=True)
class ResolvedMembership:
    tenant_id: str
    tenant_name: str
    user_id: str
    role: str
    status: str = "active"


class RequestContext(TypedDict):
    user_id: str
    tenant_id: str | None
    membership_role: str | None
    request_id: str


class AuthAdapter(Protocol):
    def authenticate(self, bearer_token: str | None) -> AuthIdentity: ...
