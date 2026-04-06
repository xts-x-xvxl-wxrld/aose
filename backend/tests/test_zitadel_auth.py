from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

jwt = pytest.importorskip("jwt")

from app.auth.errors import AuthError
from app.auth.zitadel_adapter import ZitadelAuthAdapter
from app.config import Settings


class _FakeJwkClient:
    def __init__(self, key: str) -> None:
        self._key = key

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        _ = token
        return SimpleNamespace(key=self._key)


def _build_settings(*, issuer: str = "https://issuer.example", audience: str = "api-audience") -> Settings:
    return Settings(
        _env_file=None,
        auth_mode="zitadel",
        fake_auth_enabled=False,
        zitadel_issuer=issuer,
        zitadel_audience=audience,
        zitadel_jwks_uri=f"{issuer.rstrip('/')}/oauth/v2/keys",
        zitadel_jwt_algorithms="HS256",
    )


def _build_token(
    *,
    key: str,
    issuer: str,
    audience: str,
    subject: str = "zitadel-user-123",
    expires_delta: timedelta = timedelta(minutes=5),
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "exp": now + expires_delta,
        "iat": now,
        "email": "user@example.com",
        "name": "Zitadel User",
    }
    return jwt.encode(payload, key, algorithm="HS256")


def test_zitadel_auth_adapter_authenticates_valid_token() -> None:
    settings = _build_settings()
    secret = "test-secret-key-material-32-bytes!"
    adapter = ZitadelAuthAdapter(
        issuer=settings.zitadel_issuer_normalized,
        audience=settings.zitadel_audience,
        jwks_uri=settings.zitadel_jwks_uri_resolved,
        jwt_algorithms=settings.zitadel_jwt_algorithm_list,
        jwk_client=_FakeJwkClient(secret),
    )
    token = _build_token(
        key=secret,
        issuer=settings.zitadel_issuer_normalized,
        audience=settings.zitadel_audience,
    )

    identity = adapter.authenticate(token)

    assert identity.external_auth_subject == "zitadel-user-123"
    assert identity.email == "user@example.com"
    assert identity.display_name == "Zitadel User"


def test_zitadel_auth_adapter_rejects_missing_token() -> None:
    settings = _build_settings()
    adapter = ZitadelAuthAdapter(
        issuer=settings.zitadel_issuer_normalized,
        audience=settings.zitadel_audience,
        jwks_uri=settings.zitadel_jwks_uri_resolved,
        jwt_algorithms=settings.zitadel_jwt_algorithm_list,
        jwk_client=_FakeJwkClient("unused"),
    )

    with pytest.raises(AuthError) as exc_info:
        adapter.authenticate(None)

    assert exc_info.value.error_code == "auth_required"


def test_zitadel_auth_adapter_rejects_wrong_audience() -> None:
    settings = _build_settings()
    secret = "test-secret-key-material-32-bytes!"
    adapter = ZitadelAuthAdapter(
        issuer=settings.zitadel_issuer_normalized,
        audience=settings.zitadel_audience,
        jwks_uri=settings.zitadel_jwks_uri_resolved,
        jwt_algorithms=settings.zitadel_jwt_algorithm_list,
        jwk_client=_FakeJwkClient(secret),
    )
    token = _build_token(
        key=secret,
        issuer=settings.zitadel_issuer_normalized,
        audience="different-audience",
    )

    with pytest.raises(AuthError) as exc_info:
        adapter.authenticate(token)

    assert exc_info.value.error_code == "auth_invalid_token"
    assert exc_info.value.details == {"reason": "invalid_audience"}
