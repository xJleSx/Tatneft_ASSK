"""Детекторы: конкретные реализации BaseDetector."""

from app.detectors.coco import CocoDetector
from app.detectors.defect import DefectDetector
from app.detectors.mock import MockDetector

__all__ = ["CocoDetector", "DefectDetector", "MockDetector"]
