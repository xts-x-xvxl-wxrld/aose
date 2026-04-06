from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProviderRetrySettings(ProviderConfigModel):
    max_attempts: int = Field(default=2, ge=1)


class ProviderTimeoutSettings(ProviderConfigModel):
    search_seconds: int = Field(default=10, ge=1)
    enrichment_seconds: int = Field(default=15, ge=1)
    research_fetch_seconds: int = Field(default=20, ge=1)


class FirecrawlSettings(ProviderConfigModel):
    api_key: str = ""
    base_url: str = "https://api.firecrawl.dev"
    timeouts: ProviderTimeoutSettings = Field(default_factory=ProviderTimeoutSettings)
    retry: ProviderRetrySettings = Field(default_factory=ProviderRetrySettings)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())


class GoogleLocalPlacesSettings(ProviderConfigModel):
    api_key: str = ""
    base_url: str = "https://places.googleapis.com"
    timeouts: ProviderTimeoutSettings = Field(default_factory=ProviderTimeoutSettings)
    retry: ProviderRetrySettings = Field(default_factory=ProviderRetrySettings)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())


class FindymailSettings(ProviderConfigModel):
    api_key: str = ""
    base_url: str = "https://app.findymail.com"
    timeouts: ProviderTimeoutSettings = Field(default_factory=ProviderTimeoutSettings)
    retry: ProviderRetrySettings = Field(default_factory=ProviderRetrySettings)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())


class TombaSettings(ProviderConfigModel):
    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://api.tomba.io"
    timeouts: ProviderTimeoutSettings = Field(default_factory=ProviderTimeoutSettings)
    retry: ProviderRetrySettings = Field(default_factory=ProviderRetrySettings)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip() and self.api_secret.strip())


class OpenAIProviderSettings(ProviderConfigModel):
    api_key: str = ""
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeouts: ProviderTimeoutSettings = Field(default_factory=ProviderTimeoutSettings)
    retry: ProviderRetrySettings = Field(default_factory=ProviderRetrySettings)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())


class Settings(BaseSettings):
    app_name: str = "Agentic OSE"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    auth_mode: str | None = None
    openai_agent_model: str = "gpt-5.4-mini"
    openai_reasoning_model: str | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "agentic_ose"
    postgres_user: str = "agentic"
    postgres_password: str = "agentic"
    database_url: str | None = None
    database_echo: bool = False
    fake_auth_enabled: bool = True
    fake_auth_user_id: str = "user_dev"
    fake_auth_subject: str = "dev-user"
    fake_auth_email: str = "dev@agentic-ose.local"
    fake_auth_display_name: str = "Local Dev User"
    fake_auth_tenant_id: str = "tenant_dev"
    fake_auth_tenant_name: str = "Local Dev Tenant"
    fake_auth_membership_role: str = "owner"
    fake_auth_platform_admin: bool = True
    tenant_self_serve_creation_enabled: bool = True
    zitadel_issuer: str = ""
    zitadel_audience: str = ""
    zitadel_jwks_uri: str = ""
    zitadel_jwt_algorithms: str = "RS256"
    zitadel_jwks_timeout_seconds: int = 30
    openai_api_key: str = ""
    firecrawl_api_key: str = ""
    firecrawl_base_url: str = "https://api.firecrawl.dev"
    google_local_places_api_key: str = ""
    google_local_places_base_url: str = "https://places.googleapis.com"
    findymail_api_key: str = ""
    findymail_base_url: str = "https://app.findymail.com"
    tomba_api_key: str = ""
    tomba_api_secret: str = ""
    tomba_base_url: str = "https://api.tomba.io"
    openai_base_url: str = "https://api.openai.com/v1"
    provider_search_timeout_seconds: int = 10
    provider_enrichment_timeout_seconds: int = 15
    provider_research_fetch_timeout_seconds: int = 20
    provider_max_retry_attempts: int = 2

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    @property
    def database_url_resolved(self) -> str:
        if self.database_url:
            return self.database_url

        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def alembic_database_url(self) -> str:
        return self.database_url_resolved.replace("postgresql+asyncpg://", "postgresql+psycopg://")

    @property
    def resolved_auth_mode(self) -> str:
        if self.auth_mode:
            return self.auth_mode.strip().lower()
        return "fake" if self.fake_auth_enabled else "zitadel"

    @property
    def zitadel_issuer_normalized(self) -> str:
        return self.zitadel_issuer.strip().rstrip("/")

    @property
    def zitadel_jwks_uri_resolved(self) -> str:
        if self.zitadel_jwks_uri.strip():
            return self.zitadel_jwks_uri.strip()
        issuer = self.zitadel_issuer_normalized
        if not issuer:
            return ""
        return f"{issuer}/oauth/v2/keys"

    @property
    def zitadel_jwt_algorithm_list(self) -> tuple[str, ...]:
        algorithms = tuple(
            value.strip()
            for value in self.zitadel_jwt_algorithms.split(",")
            if value.strip()
        )
        return algorithms or ("RS256",)

    @property
    def provider_timeouts(self) -> ProviderTimeoutSettings:
        return ProviderTimeoutSettings(
            search_seconds=self.provider_search_timeout_seconds,
            enrichment_seconds=self.provider_enrichment_timeout_seconds,
            research_fetch_seconds=self.provider_research_fetch_timeout_seconds,
        )

    @property
    def provider_retry(self) -> ProviderRetrySettings:
        return ProviderRetrySettings(max_attempts=self.provider_max_retry_attempts)

    @property
    def firecrawl(self) -> FirecrawlSettings:
        return FirecrawlSettings(
            api_key=self.firecrawl_api_key,
            base_url=self.firecrawl_base_url,
            timeouts=self.provider_timeouts,
            retry=self.provider_retry,
        )

    @property
    def google_local_places(self) -> GoogleLocalPlacesSettings:
        return GoogleLocalPlacesSettings(
            api_key=self.google_local_places_api_key,
            base_url=self.google_local_places_base_url,
            timeouts=self.provider_timeouts,
            retry=self.provider_retry,
        )

    @property
    def findymail(self) -> FindymailSettings:
        return FindymailSettings(
            api_key=self.findymail_api_key,
            base_url=self.findymail_base_url,
            timeouts=self.provider_timeouts,
            retry=self.provider_retry,
        )

    @property
    def tomba(self) -> TombaSettings:
        return TombaSettings(
            api_key=self.tomba_api_key,
            api_secret=self.tomba_api_secret,
            base_url=self.tomba_base_url,
            timeouts=self.provider_timeouts,
            retry=self.provider_retry,
        )

    @property
    def openai(self) -> OpenAIProviderSettings:
        return OpenAIProviderSettings(
            api_key=self.openai_api_key,
            model=self.openai_reasoning_model or self.openai_agent_model,
            base_url=self.openai_base_url,
            timeouts=self.provider_timeouts,
            retry=self.provider_retry,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
