"""Smoke-тесты CV-сервиса: /health, /readyz, /infer.

Тесты, требующие torch/ultralytics/веса, помечены @needs_torch / @needs_weights
и пропускаются, если зависимостей нет. /health и /detectors работают без torch.
"""
from __future__ import annotations

import io

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import app
from tests.conftest import needs_torch, needs_weights


def _make_jpeg_bytes() -> bytes:
    """Минимальный валидный JPEG (1x1 белый пиксель)."""
    img = Image.new("RGB", (1, 1), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------- /health (без torch) ----------


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


# ---------- /detectors (без torch, без warmup) ----------


@pytest.mark.asyncio
async def test_detectors_lists_defect():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/detectors")
    assert r.status_code == 200
    body = r.json()
    # active может быть "yolov8-base" если lifespan не успел, и "defect-yolov8" после warmup
    assert body["supported"] == ["defect"]


# ---------- /infer: ошибки валидации (без torch) ----------


@pytest.mark.asyncio
async def test_infer_empty_file_is_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/infer",
            files={"file": ("empty.jpg", b"", "image/jpeg")},
        )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_infer_garbage_jpeg_is_400():
    """Битый JPEG: 400 (декодирование падает до torch)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/infer",
            files={"file": ("bad.jpg", b"not-a-real-jpeg-bytes", "image/jpeg")},
        )
    assert r.status_code == 400
    assert "декодировать" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_infer_oversize_is_413():
    big = b"\xff\xd8\xff\xe0" + b"\x00" * (16 * 1024 * 1024)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/infer",
            files={"file": ("big.jpg", big, "image/jpeg")},
        )
    # 413 предпочтительнее, но 400 (если PIL упал на verify) тоже ок
    assert r.status_code in (400, 413)


# ---------- /infer: настоящий детектор (нужны torch + weights) ----------


@needs_torch
@needs_weights
@pytest.mark.asyncio
async def test_infer_returns_defect_detections():
    """Реальный детектор: 200 + detections в формате DefectDetector."""
    from app.config import get_settings
    from app.factory import build_detector

    get_settings.cache_clear()
    det = build_detector(get_settings())
    det.warmup()
    app.state.detector = det

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/infer",
            files={"file": ("test.jpg", _make_jpeg_bytes(), "image/jpeg")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["detector"] == "defect-yolov8"
    assert "latency_ms" in body
    assert "image_size" in body
    for d in body["detections"]:
        assert d["label"] in ("corrosion", "leak", "damage")
        assert 0.0 <= d["confidence"] <= 1.0
        assert "severity" in d["meta"]
        assert d["meta"]["severity"] in (1, 2, 3)


# ---------- /readyz (нужен прогретый детектор) ----------


@needs_torch
@needs_weights
@pytest.mark.asyncio
async def test_readyz_with_defect():
    from app.config import get_settings
    from app.factory import build_detector

    get_settings.cache_clear()
    det = build_detector(get_settings())
    det.warmup()
    app.state.detector = det

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/readyz")
    assert r.status_code == 200, r.text
    assert r.json()["detector"] == "defect-yolov8"
