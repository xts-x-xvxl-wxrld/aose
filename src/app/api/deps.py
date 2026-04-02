from typing import Annotated
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status

from app.agents.registry import AgentSystem
from app.auth.fake_adapter import FakeAuthAdapter
from app.auth.types import AuthIdentity, RequestContext, ResolvedMembership, ResolvedUser
from app.config import Settings, get_settings
from app.db.session import AsyncSession, get_db_session, get_optional_db_session
from app.models import User
from app.repositories.user_repository import UserRepository
from app.services.errors import ServiceError
from app.services.runtime import WorkflowExecutor
from app.services.tenancy import TenancyService

try:
    from sqlalchemy.exc import SQLAlchemyError
except ModuleNotFoundError:  # pragma: no cover - dev dependency guard
    SQLAlchemyError = Exception  # type: ignore[assignment]


def get_agent_system(request: Request) -> AgentSystem:
    return request.app.state.agent_system


def get_workflow_executor(request: Request) -> WorkflowExecutor:
    executor = getattr(request.app.state, "workflow_executor", None)
    if executor is None:
        raise ServiceError(
            status_code=503,
            error_code="workflow_executor_unavailable",
            message="Workflow executor is not configured for this application instance.",
        )
    return executor


def get_request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid4())


def get_settings_dependency() -> Settings:
    return get_settings()


def get_auth_adapter(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> FakeAuthAdapter:
    return FakeAuthAdapter(settings)


def get_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use the Bearer scheme.",
        )
    return token


def get_auth_identity(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    adapter: Annotated[FakeAuthAdapter, Depends(get_auth_adapter)],
    bearer_token: Annotated[str | None, Depends(get_bearer_token)],
) -> AuthIdentity:
    if not settings.fake_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Real auth is not wired yet.",
        )
    return adapter.authenticate(bearer_token)


def get_current_user(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    identity: Annotated[AuthIdentity, Depends(get_auth_identity)],
) -> ResolvedUser:
    return ResolvedUser(
        user_id=settings.fake_auth_user_id,
        external_auth_subject=identity.external_auth_subject,
        email=identity.email,
        display_name=identity.display_name,
    )


async def get_current_memberships(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    user: Annotated[ResolvedUser, Depends(get_current_user)],
    identity: Annotated[AuthIdentity, Depends(get_auth_identity)],
    db_session: Annotated[AsyncSession | None, Depends(get_optional_db_session)],
) -> list[ResolvedMembership]:
    if db_session is not None:
        try:
            persisted_memberships = await TenancyService(db_session).list_user_tenants(
                identity=identity
            )
        except SQLAlchemyError:
            persisted_memberships = []
        else:
            return [
                ResolvedMembership(
                    tenant_id=str(membership.tenant_id),
                    tenant_name=tenant.name,
                    user_id=str(membership.user_id),
                    role=membership.role,
                    status=membership.status,
                )
                for membership, tenant in persisted_memberships
            ]

    if not settings.fake_auth_enabled:
        return []

    return [
        ResolvedMembership(
            tenant_id=settings.fake_auth_tenant_id,
            tenant_name=settings.fake_auth_tenant_name,
            user_id=user.user_id,
            role=settings.fake_auth_membership_role,
        )
    ]


def get_current_membership(
    request: Request,
    memberships: Annotated[list[ResolvedMembership], Depends(get_current_memberships)],
) -> ResolvedMembership | None:
    requested_tenant_id = request.path_params.get("tenant_id")
    if requested_tenant_id is None:
        return None

    for membership in memberships:
        if membership.tenant_id == requested_tenant_id and membership.status == "active":
            return membership

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User does not have an active membership in the requested tenant.",
    )


def get_request_context(
    request_id: Annotated[str, Depends(get_request_id)],
    user: Annotated[ResolvedUser, Depends(get_current_user)],
    membership: Annotated[ResolvedMembership | None, Depends(get_current_membership)],
) -> RequestContext:
    return RequestContext(
        user_id=user.user_id,
        tenant_id=membership.tenant_id if membership else None,
        membership_role=membership.role if membership else None,
        request_id=request_id,
    )


def require_tenant_request_context(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    if context["tenant_id"] is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context is required for this endpoint.",
        )
    return context


def require_chat_request_id(request: Request) -> str:
    request_id = (request.headers.get("X-Request-ID") or "").strip()
    if not request_id:
        raise ServiceError(
            status_code=422,
            error_code="validation_error",
            message="X-Request-ID header is required for chat stream requests.",
            details={"header": "X-Request-ID"},
        )
    return request_id


async def get_persisted_actor_user(
    identity: Annotated[AuthIdentity, Depends(get_auth_identity)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    users = UserRepository(db_session)
    user = await users.get_by_external_auth_subject(
        external_auth_subject=identity.external_auth_subject
    )
    if user is None:
        user = await users.create(
            external_auth_subject=identity.external_auth_subject,
            email=identity.email,
            display_name=identity.display_name,
        )
    return user


AgentSystemDep = Annotated[AgentSystem, Depends(get_agent_system)]
WorkflowExecutorDep = Annotated[WorkflowExecutor, Depends(get_workflow_executor)]
SettingsDep = Annotated[Settings, Depends(get_settings_dependency)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
OptionalDbSessionDep = Annotated[AsyncSession | None, Depends(get_optional_db_session)]
CurrentUserDep = Annotated[ResolvedUser, Depends(get_current_user)]
CurrentMembershipsDep = Annotated[list[ResolvedMembership], Depends(get_current_memberships)]
RequestContextDep = Annotated[RequestContext, Depends(get_request_context)]
TenantRequestContextDep = Annotated[RequestContext, Depends(require_tenant_request_context)]
AuthIdentityDep = Annotated[AuthIdentity, Depends(get_auth_identity)]
RequestIdDep = Annotated[str, Depends(get_request_id)]
ChatRequestIdDep = Annotated[str, Depends(require_chat_request_id)]
PersistedActorUserDep = Annotated[User, Depends(get_persisted_actor_user)]
