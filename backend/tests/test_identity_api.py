from fastapi.testclient import TestClient

from app.api.deps import get_auth_adapter, get_settings_dependency
from app.auth.errors import AuthError
from app.auth.types import AuthIdentity
from app.config import Settings
from app.db.session import get_optional_db_session
from app.main import create_app


def test_me_endpoint_uses_fake_auth_request_context() -> None:
    app = create_app()

    async def override_get_optional_db_session():
        yield None

    def override_get_settings() -> Settings:
        return Settings(
            _env_file=None,
            auth_mode="fake",
            fake_auth_enabled=True,
            fake_auth_platform_admin=True,
        )

    app.dependency_overrides[get_optional_db_session] = override_get_optional_db_session
    app.dependency_overrides[get_settings_dependency] = override_get_settings
    client = TestClient(app)

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user_dev"
    assert body["external_auth_subject"] == "dev-user"
    assert body["email"] == "dev@agentic-ose.local"
    assert body["is_platform_admin"] is True
    assert "request_id" in body


def test_tenants_endpoint_returns_fake_membership() -> None:
    app = create_app()

    async def override_get_optional_db_session():
        yield None

    def override_get_settings() -> Settings:
        return Settings(
            _env_file=None,
            auth_mode="fake",
            fake_auth_enabled=True,
            fake_auth_platform_admin=True,
        )

    app.dependency_overrides[get_optional_db_session] = override_get_optional_db_session
    app.dependency_overrides[get_settings_dependency] = override_get_settings
    client = TestClient(app)

    response = client.get("/api/v1/tenants")

    assert response.status_code == 200
    body = response.json()
    assert body["tenants"] == [
        {
            "tenant_id": "tenant_dev",
            "tenant_name": "Local Dev Tenant",
            "role": "owner",
            "status": "active",
        }
    ]


def test_me_endpoint_supports_real_auth_mode_without_fake_static_user_id() -> None:
    app = create_app()

    async def override_get_optional_db_session():
        yield None

    def override_get_settings() -> Settings:
        return Settings(
            _env_file=None,
            auth_mode="zitadel",
            fake_auth_enabled=False,
            zitadel_issuer="https://issuer.example",
            zitadel_audience="api-audience",
        )

    class _StubAdapter:
        def authenticate(self, bearer_token: str | None) -> AuthIdentity:
            if bearer_token == "real-user-subject":
                return AuthIdentity(
                    external_auth_subject="real-user-subject",
                    email="real@example.com",
                    display_name="Real User",
                )
            raise AuthError(
                error_code="auth_required",
                message="Bearer authentication is required.",
            )

    app.dependency_overrides[get_optional_db_session] = override_get_optional_db_session
    app.dependency_overrides[get_settings_dependency] = override_get_settings
    app.dependency_overrides[get_auth_adapter] = lambda: _StubAdapter()
    client = TestClient(app)

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer real-user-subject"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "real-user-subject"
    assert body["external_auth_subject"] == "real-user-subject"
    assert body["email"] == "real@example.com"


def test_me_endpoint_requires_bearer_auth_in_real_auth_mode() -> None:
    app = create_app()

    async def override_get_optional_db_session():
        yield None

    def override_get_settings() -> Settings:
        return Settings(
            _env_file=None,
            auth_mode="zitadel",
            fake_auth_enabled=False,
            zitadel_issuer="https://issuer.example",
            zitadel_audience="api-audience",
        )

    class _StubAdapter:
        def authenticate(self, bearer_token: str | None) -> AuthIdentity:
            if not bearer_token:
                raise AuthError(
                    error_code="auth_required",
                    message="Bearer authentication is required.",
                )
            return AuthIdentity(
                external_auth_subject="unused",
                email=None,
                display_name=None,
            )

    app.dependency_overrides[get_optional_db_session] = override_get_optional_db_session
    app.dependency_overrides[get_settings_dependency] = override_get_settings
    app.dependency_overrides[get_auth_adapter] = lambda: _StubAdapter()
    client = TestClient(app)

    response = client.get("/api/v1/me")

    assert response.status_code == 401
    body = response.json()
    assert body["error_code"] == "auth_required"
    assert body["message"] == "Bearer authentication is required."
    assert "request_id" in body


def test_tenants_endpoint_supports_real_auth_mode_without_fake_memberships() -> None:
    app = create_app()

    async def override_get_optional_db_session():
        yield None

    def override_get_settings() -> Settings:
        return Settings(
            _env_file=None,
            auth_mode="zitadel",
            fake_auth_enabled=False,
            zitadel_issuer="https://issuer.example",
            zitadel_audience="api-audience",
        )

    class _StubAdapter:
        def authenticate(self, bearer_token: str | None) -> AuthIdentity:
            if bearer_token == "real-user-subject":
                return AuthIdentity(
                    external_auth_subject="real-user-subject",
                    email="real@example.com",
                    display_name="Real User",
                )
            raise AuthError(
                error_code="auth_invalid_token",
                message="Bearer token is invalid.",
                details={"reason": "invalid_token"},
            )

    app.dependency_overrides[get_optional_db_session] = override_get_optional_db_session
    app.dependency_overrides[get_settings_dependency] = override_get_settings
    app.dependency_overrides[get_auth_adapter] = lambda: _StubAdapter()
    client = TestClient(app)

    response = client.get(
        "/api/v1/tenants",
        headers={"Authorization": "Bearer real-user-subject"},
    )

    assert response.status_code == 200
    assert response.json() == {"tenants": []}


def test_identity_endpoints_reject_malformed_bearer_header_in_real_auth_mode() -> None:
    app = create_app()

    async def override_get_optional_db_session():
        yield None

    def override_get_settings() -> Settings:
        return Settings(
            _env_file=None,
            auth_mode="zitadel",
            fake_auth_enabled=False,
            zitadel_issuer="https://issuer.example",
            zitadel_audience="api-audience",
        )

    class _StubAdapter:
        def authenticate(self, bearer_token: str | None) -> AuthIdentity:
            _ = bearer_token
            raise AssertionError("Malformed Authorization headers should fail before adapter auth.")

    app.dependency_overrides[get_optional_db_session] = override_get_optional_db_session
    app.dependency_overrides[get_settings_dependency] = override_get_settings
    app.dependency_overrides[get_auth_adapter] = lambda: _StubAdapter()
    client = TestClient(app)

    response = client.get("/api/v1/me", headers={"Authorization": "Token not-bearer"})

    assert response.status_code == 401
    body = response.json()
    assert body["error_code"] == "auth_invalid_token"
    assert body["message"] == "Authorization header must use the Bearer scheme."


def test_identity_endpoints_preserve_invalid_token_reason_details_in_real_auth_mode() -> None:
    app = create_app()

    async def override_get_optional_db_session():
        yield None

    def override_get_settings() -> Settings:
        return Settings(
            _env_file=None,
            auth_mode="zitadel",
            fake_auth_enabled=False,
            zitadel_issuer="https://issuer.example",
            zitadel_audience="api-audience",
        )

    class _StubAdapter:
        def authenticate(self, bearer_token: str | None) -> AuthIdentity:
            if bearer_token == "expired-token":
                raise AuthError(
                    error_code="auth_invalid_token",
                    message="Bearer token is expired.",
                    details={"reason": "expired"},
                )
            raise AuthError(
                error_code="auth_required",
                message="Bearer authentication is required.",
            )

    app.dependency_overrides[get_optional_db_session] = override_get_optional_db_session
    app.dependency_overrides[get_settings_dependency] = override_get_settings
    app.dependency_overrides[get_auth_adapter] = lambda: _StubAdapter()
    client = TestClient(app)

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer expired-token"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error_code"] == "auth_invalid_token"
    assert body["message"] == "Bearer token is expired."
    assert body["details"] == {"reason": "expired"}
