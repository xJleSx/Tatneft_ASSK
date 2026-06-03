"""Настройки CV-сервиса.

Все параметры через env, чтобы деплой не требовал редактирования кода.

Приоритет выбора детектора (см. app.factory):
- DETECTOR=coco     -> CocoDetector, веса по MODEL_PATH или yolov8n.pt
- DETECTOR=defect   -> DefectDetector, весы по DEFECT_MODEL_PATH
                       (по умолчанию models/defect_yolov8n_v1/weights/best.pt)
- DETECTOR=mock     -> MockDetector (тесты)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень cv-service (родитель app/).
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DEFECT_WEIGHTS = ROOT_DIR / "models" / "defect_yolov8n_v1" / "weights" / "best.pt"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["dev", "staging", "prod"] = "dev"

    # Детектор: coco (YOLOv8 pretrained), defect (обучен на синтетике) или mock (тесты)
    detector: Literal["coco", "defect", "mock"] = "coco"

    # ---- COCO ----
    # Путь к весам YOLO. None и detector=coco -> ultralytics скачает yolov8n.pt
    model_path: str | None = None

    # ---- Defect ----
    # Путь к обученным весам дефектов. Дефолт — best.pt от `make cv-train`.
    defect_model_path: str = str(DEFAULT_DEFECT_WEIGHTS)
    defect_confidence: float = Field(default=0.25, ge=0.0, le=1.0)
    defect_iou: float = Field(default=0.45, ge=0.0, le=1.0)

    # ---- Общее ----
    device: str = "cpu"  # cpu / cuda:0 / mps
    confidence: float = Field(default=0.25, ge=0.0, le=1.0)
    iou: float = Field(default=0.45, ge=0.0, le=1.0)
    max_image_bytes: int = 15 * 1024 * 1024
    inference_timeout_ms: int = 30_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
