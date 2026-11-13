"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://fnip:fnip@localhost:5433/fnip"

    apify_token: str | None = None
    apify_actor_id: str = "vamsi-krishna/stock-market-news-collector"
    apify_timeout_secs: int = 300
    apify_max_retries: int = 3

    # Postgres-backed collection job worker (in-process poller)
    job_worker_enabled: bool = True
    job_poll_interval_secs: float = 2.0
    job_lease_seconds: int = 900
    job_max_attempts: int = 3
    job_retry_delay_secs: int = 30

    # CORS — comma-separated origins for local frontends. Do not use * in production.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Configurable collection input ceilings (must stay within Actor-safe hard caps)
    collection_max_items: int = 500
    collection_max_tickers: int = 20
    collection_max_companies: int = 20
    collection_max_search_queries: int = 10
    collection_max_hours_back: int = 720

    @field_validator(
        "collection_max_items",
        "collection_max_tickers",
        "collection_max_companies",
        "collection_max_search_queries",
        "collection_max_hours_back",
    )
    @classmethod
    def positive_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("collection limits must be >= 1")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [part.strip() for part in self.cors_origins.split(",") if part.strip()]
        if self.app_env.lower() == "production":
            origins = [origin for origin in origins if origin != "*"]
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
