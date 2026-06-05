"""Детектор дефектов на обученной YOLOv8 (corrosion / leak / damage).

Загружает кастомные весы `defect_model_path`. Если файл весов не найден —
падает с понятной ошибкой при warmup, чтобы оператор увидел проблему
в логах и в /readyz, а не при первом POST /infer.

Классы зашиты в порядке, в котором обучалась модель:
    0 -> corrosion
    1 -> leak
    2 -> damage

`meta.severity` отдаёт порядковый номер по убыванию опасности:
damage > leak > corrosion — для приоритизации ремонта в бекенде.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.detectors.base import Detection
from app.detectors.yolo import _YoloBase

log = logging.getLogger(__name__)

DEFECT_CLASSES: tuple[str, ...] = ("corrosion", "leak", "damage")

DEFECT_SEVERITY: dict[str, int] = {
    "corrosion": 1,
    "leak": 2,
    "damage": 3,
}


class DefectDetector(_YoloBase):
    name = "defect-yolov8"

    def __init__(self, model_path: str, device: str, conf: float, iou: float) -> None:
        if not model_path:
            raise ValueError(
                "DefectDetector требует путь к весам (defect_model_path)."
            )
        if not Path(model_path).is_file():
            raise FileNotFoundError(
                f"Файл весов дефектов не найден: {model_path}."
            )
        super().__init__(model_path=model_path, device=device, conf=conf, iou=iou)
        log.info("DefectDetector готов: weights=%s, classes=%s", model_path, DEFECT_CLASSES)

    def _class_meta(self, cls_id: int, label: str) -> dict:
        expected = DEFECT_CLASSES[cls_id] if 0 <= cls_id < len(DEFECT_CLASSES) else label
        return {
            "class_id": int(cls_id),
            "expected_label": expected,
            "severity": DEFECT_SEVERITY.get(expected, 0),
        }

    def _postprocess(self, result: Any) -> list[Detection]:
        out = super()._postprocess(result)
        for d in out:
            d.meta.setdefault("severity", DEFECT_SEVERITY.get(d.label, 0))
        return out
