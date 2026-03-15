from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FastAPI URL Shortener"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    base_url: str = ""

    database_url: str = "sqlite:///./shortener.db"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60 * 24
    algorithm: str = "HS256"

    default_inactive_days: int = 30
    cache_ttl_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
