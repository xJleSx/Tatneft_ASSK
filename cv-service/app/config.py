"""Настройки CV-сервиса.

Все параметры через env, чтобы деплой не требовал редактирования кода.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["dev", "staging", "prod"] = "dev"

    # Детектор: coco (YOLOv8 pretrained) или defect (заглушка, ожидает обучения)
    detector: Literal["coco", "defect", "mock"] = "coco"

    # Путь к весам YOLO. Если None и detector=coco — используется yolov8n.pt
    # (ultralytics сам скачает при первом запуске).
    model_path: str | None = None

    # Устройство инференса: cpu / cuda:0 / mps (Apple Silicon)
    device: str = "cpu"

    # Минимальная уверенность детекции (0..1)
    confidence: float = Field(default=0.25, ge=0.0, le=1.0)

    # IoU-порог для NMS
    iou: float = Field(default=0.45, ge=0.0, le=1.0)

    # Максимальный размер загружаемого изображения (байт)
    max_image_bytes: int = 15 * 1024 * 1024

    # Таймаут одного инференса (мс)
    inference_timeout_ms: int = 30_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
