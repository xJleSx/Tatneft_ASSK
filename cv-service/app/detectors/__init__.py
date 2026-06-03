"""Детекторы: конкретные реализации BaseDetector."""

from app.detectors.coco import CocoDetector
from app.detectors.defect import DEFECT_CLASSES, DefectDetector
from app.detectors.mock import MockDetector

__all__ = ["DEFECT_CLASSES", "CocoDetector", "DefectDetector", "MockDetector"]
