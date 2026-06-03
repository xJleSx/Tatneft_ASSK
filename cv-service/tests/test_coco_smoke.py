"""Smoke-тест CocoDetector (YOLOv8) на реальном фото.

Требует установленных ultralytics + torch. Если их нет — тест
пропускается (это нормально: проект собирается без ML-зависимостей,
тесты на MockDetector покрывают остальную логику).

Что проверяем:
- CocoDetector.warmup() грузит yolov8n.pt
- detect() на реальном фото находит >=1 объект
- среди лейблов есть 'person' (Pexels 220453 — портрет)

БЕЗ этого теста CI не поймает регрессию вроде 'yolov8n.pt сменил
формат' или 'ultralytics сломал API'.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from app.detectors.coco import CocoDetector

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "sample_person.jpg"
)


def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not _torch_available(),
    reason="torch/ultralytics не установлены (тест на MockDetector покрывает остальное)",
)


@pytest.mark.skipif(not FIXTURE.exists(), reason=f"Нет фикстуры {FIXTURE}")
@pytest.mark.asyncio
async def test_coco_detector_finds_person_on_real_photo():
    """Реальное фото из Pexels: YOLOv8 должен найти хотя бы одного person."""
    from app.detectors.coco import CocoDetector

    det = CocoDetector(model_path=None, device="cpu", conf=0.25, iou=0.45)
    det.warmup()

    image_bytes = FIXTURE.read_bytes()
    detections = det.detect(image_bytes)

    labels = [d.label for d in detections]
    confidences = [d.confidence for d in detections]

    assert len(detections) >= 1, f"YOLO ничего не нашёл на {FIXTURE.name}, метки={labels}"
    assert "person" in labels, f"YOLO не нашёл 'person', метки={labels}, confs={confidences}"
    # Уверенность на Pexels-портрете обычно > 0.5
    best_person = max(d.confidence for d in detections if d.label == "person")
    assert best_person >= 0.3, f"person conf слишком низкий: {best_person}"


@pytest.mark.asyncio
async def test_coco_detector_returns_empty_for_noise():
    """Синтетический шум: count=0 (но inference не падает)."""
    import io

    from PIL import Image

    from app.detectors.coco import CocoDetector

    det = CocoDetector(model_path=None, device="cpu", conf=0.25, iou=0.45)
    det.warmup()

    import random

    rng = random.Random(42)
    img = Image.new("RGB", (640, 480))
    px = img.load()
    for y in range(480):
        for x in range(640):
            px[x, y] = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)

    detections = det.detect(buf.getvalue())
    assert detections == [], f"На шуме ожидался [], получили {len(detections)} детекций"


@pytest.mark.asyncio
async def test_synth_real_photo_scene_via_factory():
    """build_scene('real_photo') + CocoDetector — end-to-end."""
    from app.synth import build_scene

    scene = build_scene("real_photo")
    assert scene.image_bytes, "real_photo сцена не сгенерировалась"
    assert scene.expected_label == "person"

    det = _build_coco()
    det.warmup()
    detections = det.detect(scene.image_bytes)
    labels = [d.label for d in detections]
    assert "person" in labels, f"YOLO не нашёл person на real_photo, метки={labels}"


def _build_coco() -> CocoDetector:
    from app.detectors.coco import CocoDetector

    return CocoDetector(model_path=None, device="cpu", conf=0.25, iou=0.45)
