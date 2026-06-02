"""Конфигурация приложения."""
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "askk-prototype"
    app_env: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"

    secret_key: str = "dev-only-do-not-use-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 60
    jwt_refresh_ttl_days: int = 14

    database_url: str = "postgresql+asyncpg://askk:askk@localhost:5432/askk"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "askk-photos"
    minio_secure: bool = False

    redis_url: str = "redis://localhost:6379/0"

    asutp_mode: Literal["mock", "opcua", "rest"] = "mock"
    asutp_mock_interval_sec: int = 60

    geo_radius_m: int = 75

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
