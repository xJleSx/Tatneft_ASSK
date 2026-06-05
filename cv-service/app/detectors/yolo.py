"""YOLO-инференс для `DefectDetector`.

Вынесен в отдельный модуль, чтобы:
- не дублировать ~50 строк YOLO.predict + postprocess,
- дать детектору понятный контракт ошибок (400 на битый JPEG),
- держать lazy import ultralytics в одном месте.

Подклассы переопределяют только `name` и (опционально) маппинг классов.
"""
from __future__ import annotations

import io
import logging
from typing import Any

from PIL import Image

from app.detectors.base import BaseDetector, Detection

log = logging.getLogger(__name__)


class _YoloBase(BaseDetector):
    """База для YOLOv8-детекторов с кастомными весами."""

    name: str = "yolov8-base"

    def __init__(
        self,
        model_path: str,
        device: str,
        conf: float,
        iou: float,
    ) -> None:
        self._model_path = model_path
        self._device = device
        self._conf = conf
        self._iou = iou
        self._model: Any = None

    def warmup(self) -> None:
        from ultralytics import YOLO

        log.info("Loading YOLO model: %s on %s", self._model_path, self._device)
        self._model = YOLO(self._model_path)
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

    def _postprocess(self, result: Any) -> list[Detection]:
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
        return {"class_id": int(cls_id)}
