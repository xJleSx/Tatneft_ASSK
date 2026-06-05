"""Фабрика детекторов по настройкам.

Используется при старте CV-сервиса. Единственная поддерживаемая
конфигурация: `DETECTOR=defect` (YOLOv8, обученная на 3 классах
дефектов оборудования: corrosion / leak / damage).

При старте обязателен существующий файл весов (`weights/defect.pt`).
Если его нет — падаем с FileNotFoundError, чтобы оператор увидел
проблему в логах при старте, а не при первом /infer.
"""
from __future__ import annotations

import logging

from app.config import Settings
from app.detectors.base import BaseDetector
from app.detectors.defect import DefectDetector

log = logging.getLogger(__name__)


def build_detector(settings: Settings) -> BaseDetector:
    kind = settings.detector.lower()
    if kind == "defect":
        log.info(
            "Building DefectDetector (path=%s, device=%s, conf=%.2f)",
            settings.defect_model_path,
            settings.device,
            settings.defect_confidence,
        )
        return DefectDetector(
            model_path=settings.defect_model_path,
            device=settings.device,
            conf=settings.defect_confidence,
            iou=settings.defect_iou,
        )
    raise ValueError(f"Unknown detector: {settings.detector!r}")
