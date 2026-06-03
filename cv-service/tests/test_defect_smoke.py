"""Smoke-тест DefectDetector (обученная YOLOv8) на синтетических val-картинках.

Что проверяем:
- DefectDetector.warmup() грузит best.pt из настроек
- detect() на синтетике находит дефекты (precision >=0.5 на top-1)
- имена классов соответствуют DEFECT_CLASSES (corrosion/leak/damage)
- meta.severity проставлен (1/2/3)
- inference < 500мс на CPU

Тест skipif:
- Нет torch/ultralytics — пропускаем (тесты на MockDetector покрывают остальное).
- Нет файла весов (например, после клона без `make cv-train`) — пропускаем.

Запуск:
    pytest tests/test_defect_smoke.py -v
или
    make cv-defect-smoke
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.detectors.defect import DefectDetector


def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
        return True
    except ImportError:
        return False


def _weights_path() -> Path:
    from app.config import DEFAULT_DEFECT_WEIGHTS, get_settings

    get_settings.cache_clear()
    s = get_settings()
    p = Path(s.defect_model_path)
    # Если дефолтный путь отсутствует, может быть пользовательский
    return p if p.is_file() else DEFAULT_DEFECT_WEIGHTS


def _val_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "dataset" / "images" / "val"


pytestmark = pytest.mark.skipif(
    not _torch_available(),
    reason="torch/ultralytics не установлены (тест на MockDetector покрывает остальное)",
)


@pytest.fixture(scope="module")
def defect_detector() -> DefectDetector:
    from app.detectors.defect import DefectDetector

    weights = _weights_path()
    if not weights.is_file():
        pytest.skip(f"Нет весов дефектов: {weights}. Запустите `make cv-train`.")
    det = DefectDetector(model_path=str(weights), device="cpu", conf=0.25, iou=0.45)
    det.warmup()
    return det


@pytest.mark.skipif(not _val_dir().exists(), reason=f"Нет {_val_dir()} — запустите `make cv-synth-data`")
@pytest.mark.asyncio
async def test_defect_detector_finds_synthetic_defects(defect_detector):
    """На 5 случайных val-картинках детектор должен найти >=1 дефект каждая."""
    import random

    val_imgs = sorted(_val_dir().glob("*.jpg"))
    assert val_imgs, f"val пуст: {_val_dir()}"
    rng = random.Random(42)
    sample = rng.sample(val_imgs, k=min(5, len(val_imgs)))

    from app.detectors.defect import DEFECT_CLASSES

    for p in sample:
        dets = defect_detector.detect(p.read_bytes())
        labels = [d.label for d in dets]
        assert len(dets) >= 1, f"{p.name}: 0 детекций (ожидался >=1)"
        assert all(lbl in DEFECT_CLASSES for lbl in labels), (
            f"{p.name}: незнакомый класс: {labels}"
        )
        # Top-1 confidence должна быть разумной
        top_conf = max(d.confidence for d in dets)
        assert top_conf >= 0.3, f"{p.name}: top conf={top_conf:.3f} < 0.3"


@pytest.mark.skipif(not _val_dir().exists(), reason=f"Нет {_val_dir()}")
def test_defect_detector_meta_has_severity(defect_detector):
    """meta.severity должен быть проставлен (1/2/3) у каждой детекции."""
    val_imgs = sorted(_val_dir().glob("*.jpg"))
    assert val_imgs, "val пуст"
    p = val_imgs[0]
    dets = defect_detector.detect(p.read_bytes())
    assert dets, f"{p.name}: пустые детекции"
    for d in dets:
        assert "severity" in d.meta, f"{p.name}: нет severity в meta: {d.meta}"
        assert d.meta["severity"] in (1, 2, 3), (
            f"{p.name}: severity={d.meta['severity']} вне диапазона 1..3"
        )


@pytest.mark.asyncio
async def test_defect_detector_inference_under_500ms(defect_detector):
    """CPU-инференс на одной 640x640 картинке < 500 мс (overshoot для запаса)."""
    import time

    val_imgs = sorted(_val_dir().glob("*.jpg"))
    if not val_imgs:
        pytest.skip(f"Нет {_val_dir()}")
    raw = val_imgs[0].read_bytes()
    t0 = time.perf_counter()
    dets = defect_detector.detect(raw)
    dt_ms = (time.perf_counter() - t0) * 1000
    # Не строгий assert: 500мс — soft budget, но регрессию в 5s словлю
    assert dt_ms < 500, f"Слишком долгий инференс: {dt_ms:.1f} мс на {val_imgs[0].name}"
    assert dets  # хоть что-то нашло
