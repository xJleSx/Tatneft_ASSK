"""YOLOv8 (ultralytics) на COCO — общая детекция объектов.

Использует претренированные веса yolov8n.pt (ultralytics сам скачает при первом
запуске). В проде будет заменён на дообученную модель (DefectDetector), но
оставлен как fallback и для не-нефтегазовых задач (общая разметка фото).
"""
from __future__ import annotations

from app.detectors.yolo import _YoloBase


class CocoDetector(_YoloBase):
    name = "yolov8-coco"
