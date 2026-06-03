"""Конфигурация приложения."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

# Значения, которые НЕЛЬЗЯ использовать в не-dev окружениях.
# В проде SECRET_KEY должен приходить из .env / секрет-стора.
_FORBIDDEN_SECRETS = frozenset(
    {
        "dev-only-do-not-use-in-prod",
        "change-me-in-prod-very-long-random-string-please",
        "",
    }
)


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

    # CV-сервис (YOLOv8 и т.п.) — отдельный микросервис в docker-compose
    cv_service_url: str = "http://cv:8000"
    cv_timeout_s: float = 30.0
    cv_enabled: bool = True

    geo_radius_m: int = 75

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _validate_prod_safety(self) -> Settings:
        """Строгие проверки для не-dev окружений."""
        if self.app_env == "dev":
            return self

        # 1) SECRET_KEY: не placeholder, >= 32 символов
        if self.secret_key in _FORBIDDEN_SECRETS:
            raise ValueError(
                f"app_env={self.app_env}: SECRET_KEY is a known placeholder. "
                "Set a strong random value (>=32 chars) via environment or .env"
            )
        if len(self.secret_key) < 32:
            raise ValueError(
                f"app_env={self.app_env}: SECRET_KEY must be at least 32 chars "
                f"(got {len(self.secret_key)})"
            )

        # 2) CORS: в проде запрещены wildcard и http://
        origins = self.cors_origins_list
        if "*" in origins:
            raise ValueError(
                f"app_env={self.app_env}: CORS_ORIGINS must not contain '*' (CORS spec "
                "disallows wildcard with credentials)"
            )
        for o in origins:
            if o.startswith("http://") and not o.startswith("http://localhost"):
                raise ValueError(
                    f"app_env={self.app_env}: CORS origin {o!r} uses http://; "
                    "production must use https://"
                )

        # 3) DEBUG должен быть выключен
        if self.debug:
            log.warning("app_env=%s but DEBUG=true — disabling", self.app_env)
            self.debug = False
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
