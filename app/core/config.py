from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Deals Backend"
    api_v1_prefix: str = "/api/v1"
    postgres_server: str = "db"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "deals"
    jobs_log_dir: str = "logs/jobs"
    ai_copy_model_name: str = "stub-model"
    ai_copy_prompt_version: str = "v1"
    ai_copy_stub_response: str = (
        '{"title":"Draft unavailable","summary":"No model client configured.","verdict":"not_supported","tags":["review-needed"]}'
    )
    serpapi_api_key: str | None = None
    serpapi_engine: str = "google_shopping"
    serpapi_country: str | None = None
    serpapi_language: str | None = None
    serpapi_location: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
