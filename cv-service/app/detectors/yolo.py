"""Общий YOLO-инференс для `CocoDetector` и `DefectDetector`.

Вынесен в отдельный модуль, чтобы:
- не дублировать ~50 строк YOLO.predict + postprocess,
- дать обоим детекторам одинаковый контракт ошибок (400 на битый JPEG),
- держать lazy import ultralytics в одном месте.

Подклассы переопределяют только `name` и (опционально) маппинг классов.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image

from app.detectors.base import BaseDetector, Detection

log = logging.getLogger(__name__)


class _YoloBase(BaseDetector):
    """База для YOLOv8-детекторов (COCO-pretrained или кастомные веса)."""

    # Подклассы обязаны задать имя (отображается в /infer и /detectors).
    name: str = "yolov8-base"

    def __init__(
        self,
        model_path: str | None,
        device: str,
        conf: float,
        iou: float,
    ) -> None:
        self._model_path = model_path
        self._device = device
        self._conf = conf
        self._iou = iou
        self._model: Any = None  # ultralytics.YOLO; lazy, чтобы тесты с Mock не тянули torch

    # ----- lifecycle -----

    def warmup(self) -> None:
        # Импорт тут: ultralytics тяжёлый, тестам с MockDetector не нужен.
        from ultralytics import YOLO

        path = self._model_path or "yolov8n.pt"
        log.info("Loading YOLO model: %s on %s", path, self._device)
        self._model = YOLO(path)
        try:
            self._model.predict(
                source=Image.new("RGB", (64, 64), color=(0, 0, 0)),
                device=self._device,
                conf=self._conf,
                iou=self._iou,
                verbose=False,
            )
        except Exception as e:
            log.warning("YOLO warmup predict failed (продолжаем): %s", e)

    # ----- inference -----

    def detect(self, image_bytes: bytes) -> list[Detection]:
        if self._model is None:
            raise RuntimeError("Detector not warmed up. Call warmup() at startup.")

        try:
            img = Image.open(io.BytesIO(image_bytes))
        except Exception as e:
            raise ValueError(f"Не удалось декодировать изображение: {e}") from e

        results = self._model.predict(
            source=img,
            device=self._device,
            conf=self._conf,
            iou=self._iou,
            verbose=False,
        )
        if not results:
            return []
        return self._postprocess(results[0])

    # ----- postprocess -----

    def _postprocess(self, result: Any) -> list[Detection]:
        """Парсим ultralytics result в список Detection.

        По умолчанию берём имена классов из `result.names` (как у CocoDetector).
        DefectDetector переопределяет, если нужно заменить индексы на свои
        (например, чтобы положить `severity` в meta).
        """
        names: dict[int, str] = result.names
        boxes = result.boxes
        if boxes is None:
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy().astype(int)

        out: list[Detection] = []
        for (x_min, y_min, x_max, y_max), confidence, cls_id in zip(
            xyxy, confs, clss, strict=False
        ):
            label = names.get(int(cls_id), str(cls_id))
            out.append(
                Detection(
                    label=label,
                    confidence=float(confidence),
                    x_min=float(x_min),
                    y_min=float(y_min),
                    x_max=float(x_max),
                    y_max=float(y_max),
                    detector=self.name,
                    meta=self._class_meta(int(cls_id), label),
                )
            )
        return out

    def _class_meta(self, cls_id: int, label: str) -> dict:
        """Доп. мета для конкретного класса. По умолчанию — class_id."""
        return {"class_id": int(cls_id)}


def model_file_exists(path: str | None) -> bool:
    """True если путь непустой и файл существует. Используется в factory."""
    if not path:
        return False
    return Path(path).is_file()
