from __future__ import annotations

from typing import Any

try:
    import jwt
    from jwt import (
        ExpiredSignatureError,
        ImmatureSignatureError,
        InvalidAudienceError,
        InvalidIssuerError,
        InvalidSignatureError,
        InvalidTokenError,
        PyJWKClient,
    )
    from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError
except ModuleNotFoundError as exc:  # pragma: no cover - import guard for local envs
    jwt = None  # type: ignore[assignment]
    PyJWKClient = Any  # type: ignore[misc,assignment]
    ExpiredSignatureError = ImmatureSignatureError = InvalidAudienceError = InvalidIssuerError = (  # type: ignore[assignment]
        InvalidSignatureError
    ) = InvalidTokenError = PyJWKClientConnectionError = PyJWKClientError = Exception
    _IMPORT_ERROR: ModuleNotFoundError | None = exc
else:
    _IMPORT_ERROR = None

from app.auth.errors import AuthError
from app.auth.types import AuthIdentity


class ZitadelAuthAdapter:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_uri: str,
        jwt_algorithms: tuple[str, ...] = ("RS256",),
        jwks_timeout_seconds: int = 30,
        jwk_client: PyJWKClient | None = None,
    ) -> None:
        self._issuer = issuer.strip().rstrip("/")
        self._audience = audience.strip()
        self._jwks_uri = jwks_uri.strip()
        self._jwt_algorithms = jwt_algorithms
        self._jwk_client = (
            jwk_client
            if jwk_client is not None or _IMPORT_ERROR is not None
            else PyJWKClient(
                self._jwks_uri,
                cache_jwk_set=True,
                timeout=jwks_timeout_seconds,
            )
        )

    def authenticate(self, bearer_token: str | None) -> AuthIdentity:
        if not bearer_token or not bearer_token.strip():
            raise AuthError(
                error_code="auth_required",
                message="Bearer authentication is required.",
            )

        self._ensure_configured()
        token = bearer_token.strip()

        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self._jwt_algorithms),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["sub", "iss", "aud", "exp"]},
            )
        except ExpiredSignatureError as exc:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Bearer token is expired.",
                details={"reason": "expired"},
            ) from exc
        except ImmatureSignatureError as exc:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Bearer token is not active yet.",
                details={"reason": "not_active_yet"},
            ) from exc
        except InvalidAudienceError as exc:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Bearer token has an invalid audience.",
                details={"reason": "invalid_audience"},
            ) from exc
        except InvalidIssuerError as exc:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Bearer token has an invalid issuer.",
                details={"reason": "invalid_issuer"},
            ) from exc
        except InvalidSignatureError as exc:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Bearer token signature is invalid.",
                details={"reason": "invalid_signature"},
            ) from exc
        except (PyJWKClientConnectionError, PyJWKClientError) as exc:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Unable to load signing keys for bearer token validation.",
                details={"reason": "jwks_unavailable"},
            ) from exc
        except InvalidTokenError as exc:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Bearer token is invalid.",
                details={"reason": "invalid_token"},
            ) from exc

        subject = _string_claim(claims, "sub")
        if not subject:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Bearer token is missing a valid subject claim.",
                details={"reason": "missing_subject"},
            )

        return AuthIdentity(
            external_auth_subject=subject,
            email=_string_claim(claims, "email"),
            display_name=_first_string_claim(claims, "name", "preferred_username"),
        )

    def _ensure_configured(self) -> None:
        if _IMPORT_ERROR is not None:
            raise RuntimeError(
                "PyJWT is required for Zitadel auth mode. Install project dependencies before enabling AUTH_MODE=zitadel."
            ) from _IMPORT_ERROR
        if not self._issuer:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Zitadel auth issuer is not configured.",
                details={"reason": "missing_issuer"},
            )
        if not self._audience:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Zitadel auth audience is not configured.",
                details={"reason": "missing_audience"},
            )
        if not self._jwks_uri:
            raise AuthError(
                error_code="auth_invalid_token",
                message="Zitadel JWKS URI is not configured.",
                details={"reason": "missing_jwks_uri"},
            )


def zitadel_auth_dependencies_available() -> bool:
    return _IMPORT_ERROR is None


def _string_claim(claims: dict[str, Any], field_name: str) -> str | None:
    value = claims.get(field_name)
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _first_string_claim(claims: dict[str, Any], *field_names: str) -> str | None:
    for field_name in field_names:
        value = _string_claim(claims, field_name)
        if value is not None:
            return value
    return None
