"""Application configuration loaded from environment variables."""

from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
