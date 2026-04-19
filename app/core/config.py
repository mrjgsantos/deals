from functools import lru_cache

from pydantic import computed_field, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Deals Backend"
    api_v1_prefix: str = "/api/v1"

    auth_secret_key: str = "change-me-in-production-auth-secret"
    auth_token_expire_minutes: int = 60 * 24 * 7
    google_client_id: str | None = None
    google_tokeninfo_url: str = "https://oauth2.googleapis.com/tokeninfo"

    # 🔹 NOVO — override completo
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")

    # 🔹 fallback local (docker)
    postgres_server: str = "db"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "deals"

    cors_allowed_origins: list[str] = Field(default_factory=list)

    jobs_log_dir: str = "logs/jobs"

    ai_copy_model_name: str = "stub-model"
    ai_copy_prompt_version: str = "v1"
    ai_copy_stub_response: str = (
        '{"title":"Draft unavailable","summary":"No model client configured.","verdict":"not_supported","tags":["review-needed"]}'
    )

    serpapi_enabled: bool = True
    serpapi_api_key: str | None = None
    serpapi_engine: str = "google_shopping"
    serpapi_country: str | None = None
    serpapi_language: str | None = None
    serpapi_location: str | None = None
    serpapi_queries_file: str = "data/serpapi_queries.json"
    serpapi_query_limit: int = 8

    resend_api_key: str | None = None
    resend_from_email: str = "noreply@deals.app"
    app_base_url: str = "http://localhost:5173"
    password_reset_token_expire_minutes: int = 60

    debug: bool = False
    enable_api_docs: bool = False

    keepa_api_key: str | None = None
    keepa_domain_id: int = 1

    amazon_discovery_urls_file: str = "data/amazon_es_discovery_urls.txt"
    amazon_discovery_max_candidates: int = 500
    amazon_discovery_max_pages_per_url: int = 2
    amazon_discovery_domain_id: int = 9  # 9 = amazon.es

    enable_background_jobs: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @computed_field
    @property
    def database_url(self) -> str:
        # 🔥 PRIORIDADE: DATABASE_URL (produção)
        if self.database_url_override:
            return self.database_url_override

        # 🔹 fallback local
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()