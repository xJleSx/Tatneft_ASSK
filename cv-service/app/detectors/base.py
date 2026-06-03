"""Базовый интерфейс детектора.

Любая модель (YOLO, Faster R-CNN, классификатор и т.п.) реализует
`BaseDetector.detect(image_bytes) -> list[Detection]`.

Это позволяет:
- заменить YOLO на кастомную модель дефектов без изменения API,
- подменять на `MockDetector` в тестах (без torch/ultralytics),
- держать в `app.detectors` несколько реализаций рядом.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class Detection:
    """Одна найденная сущность на изображении."""

    label: str
    confidence: float
    # Bounding box в пикселях: xyxy, верхний-левый -> нижний-правый.
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    # Имя детектора (для трассировки в auto_check)
    detector: str = ""
    # Произвольные метаданные (id класса в COCO, severity дефекта и т.п.)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "bbox": {
                "x_min": round(self.x_min, 2),
                "y_min": round(self.y_min, 2),
                "x_max": round(self.x_max, 2),
                "y_max": round(self.y_max, 2),
            },
            "detector": self.detector,
            "meta": self.meta,
        }


class BaseDetector(ABC):
    """Контракт детектора."""

    name: str = "base"

    @abstractmethod
    def detect(self, image_bytes: bytes) -> list[Detection]:
        """Вернуть список детекций. Бросает ValueError на нечитаемое изображение."""

    @abstractmethod
    def warmup(self) -> None:
        """Прогреть модель (загрузить веса, проверить GPU). Вызывается при старте."""
