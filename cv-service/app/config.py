"""Настройки CV-сервиса.

Все параметры через env, чтобы деплой не требовал редактирования кода.

Поддерживается единственный детектор: `defect` (YOLOv8, обучена на трёх
классах дефектов оборудования: corrosion / leak / damage).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DEFECT_WEIGHTS = ROOT_DIR / "weights" / "defect.pt"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["dev", "staging", "prod"] = "dev"

    # Единственный детектор: defect (YOLOv8, 3 класса дефектов)
    detector: Literal["defect"] = "defect"

    # Путь к обученным весам дефектов.
    defect_model_path: str = str(DEFAULT_DEFECT_WEIGHTS)
    defect_confidence: float = Field(default=0.25, ge=0.0, le=1.0)
    defect_iou: float = Field(default=0.45, ge=0.0, le=1.0)

    device: str = "cpu"  # cpu / cuda:0 / mps
    max_image_bytes: int = 15 * 1024 * 1024
    inference_timeout_ms: int = 30_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
