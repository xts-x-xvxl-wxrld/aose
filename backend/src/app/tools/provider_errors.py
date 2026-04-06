from __future__ import annotations


class ProviderError(RuntimeError):
    error_code = "provider_unavailable"

    def __init__(self, provider_name: str, message: str | None = None) -> None:
        self.provider_name = provider_name
        super().__init__(message or f"{provider_name} request failed.")


class ProviderAuthError(ProviderError):
    error_code = "provider_auth_error"


class ProviderRateLimitError(ProviderError):
    error_code = "provider_rate_limit"


class ProviderQuotaError(ProviderError):
    error_code = "provider_quota_exceeded"


class ProviderUnavailableError(ProviderError):
    error_code = "provider_unavailable"


class ProviderBadResponseError(ProviderError):
    error_code = "provider_bad_response"
