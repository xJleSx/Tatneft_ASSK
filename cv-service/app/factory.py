"""Фабрика детекторов по настройкам.

Используется при старте CV-сервиса и пересоздаёт детектор при изменении
`detector` в env (hot-reload не реализован — перезапуск сервиса).
"""

from __future__ import annotations

import logging

from app.config import Settings
from app.detectors.base import BaseDetector
from app.detectors.coco import CocoDetector
from app.detectors.defect import DefectDetector
from app.detectors.mock import MockDetector

log = logging.getLogger(__name__)


def build_detector(settings: Settings) -> BaseDetector:
    kind = settings.detector.lower()
    if kind == "coco":
        log.info("Building CocoDetector (path=%s, device=%s)", settings.model_path, settings.device)
        return CocoDetector(
            model_path=settings.model_path,
            device=settings.device,
            conf=settings.confidence,
            iou=settings.iou,
        )
    if kind == "defect":
        log.info("Building DefectDetector (stub mode)")
        return DefectDetector()
    if kind == "mock":
        log.info("Building MockDetector (no weights)")
        return MockDetector()
    raise ValueError(f"Unknown detector: {settings.detector!r}")
