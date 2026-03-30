from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agentic OSE"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    openai_agent_model: str = "gpt-5.4-mini"
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
