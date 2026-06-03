"""YOLOv8 (ultralytics) на COCO.

Placeholder для MVP. В проде будет заменён на дообученную модель
дефектов оборудования (коррозия, утечки и т.п.).

Веса:
- По умолчанию ultralytics скачивает yolov8n.pt (~6 MB) при первом запуске.
- Можно переопределить через CV_MODEL_PATH=/path/to/custom.pt
  (например, после обучения на своих данных).
"""

from __future__ import annotations

import io
import logging
from typing import Any

from PIL import Image

from app.detectors.base import BaseDetector, Detection

log = logging.getLogger(__name__)


class CocoDetector(BaseDetector):
    name = "yolov8-coco"

    def __init__(self, model_path: str | None, device: str, conf: float, iou: float):
        self._model_path = model_path  # None -> yolov8n.pt
        self._device = device
        self._conf = conf
        self._iou = iou
        self._model: Any = None  # ultralytics.YOLO; lazy

    def warmup(self) -> None:
        # Импорт тут: ultralytics тяжёлый (тянет torch), и тестам с MockDetector
        # этот модуль не нужен.
        from ultralytics import YOLO

        log.info("Loading YOLO model: %s on %s", self._model_path or "yolov8n.pt", self._device)
        self._model = YOLO(self._model_path or "yolov8n.pt")
        # Холостой прогон на 64x64 для компиляции графа (если torch.compile)
        try:
            self._model.predict(
                source=Image.new("RGB", (64, 64), color=(0, 0, 0)),
                device=self._device,
                conf=self._conf,
                iou=self._iou,
                verbose=False,
            )
        except Exception as e:
            log.warning("YOLO warmup failed (продолжаем): %s", e)

    def detect(self, image_bytes: bytes) -> list[Detection]:
        if self._model is None:
            raise RuntimeError("Detector not warmed up. Call warmup() at startup.")

        try:
            img = Image.open(io.BytesIO(image_bytes))
        except Exception as e:
            raise ValueError(f"Не удалось декодировать изображение: {e}") from e

        # ultralytics принимает PIL.Image, numpy.ndarray, путь. PIL ок.
        results = self._model.predict(
            source=img,
            device=self._device,
            conf=self._conf,
            iou=self._iou,
            verbose=False,
        )
        if not results:
            return []

        result = results[0]
        names: dict[int, str] = result.names  # class_id -> label
        boxes = result.boxes
        if boxes is None:
            return []

        out: list[Detection] = []
        # boxes.xyxy, boxes.conf, boxes.cls — torch.Tensor
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy().astype(int)
        for (x_min, y_min, x_max, y_max), confidence, cls_id in zip(xyxy, confs, clss, strict=False):
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
                    meta={"coco_class_id": int(cls_id)},
                )
            )
        return out
