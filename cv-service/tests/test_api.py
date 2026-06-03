"""Smoke-тесты CV-сервиса: /health, /readyz, /infer — на MockDetector (без torch)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.detectors.mock import make_test_jpeg


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_readyz_with_mock(client: AsyncClient):
    r = await client.get("/readyz")
    assert r.status_code == 200, r.text
    assert r.json()["detector"] == "mock"


@pytest.mark.asyncio
async def test_list_detectors(client: AsyncClient):
    r = await client.get("/detectors")
    assert r.status_code == 200
    body = r.json()
    assert body["active"] == "mock"
    assert "coco" in body["supported"]


@pytest.mark.asyncio
async def test_infer_returns_fixed_detections(client: AsyncClient):
    jpeg = make_test_jpeg()
    r = await client.post(
        "/infer",
        files={"file": ("test.jpg", jpeg, "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["detector"] == "mock"
    assert body["count"] == 1
    det = body["detections"][0]
    assert det["label"] == "test_object"
    assert det["confidence"] == 0.91
    assert det["bbox"]["x_min"] == 10
    assert det["meta"]["source"] == "fixture"
    assert body["image_size"]["width"] == 640
    assert body["image_size"]["height"] == 480


@pytest.mark.asyncio
async def test_infer_empty_file_is_400(client: AsyncClient):
    r = await client.post(
        "/infer",
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_infer_garbage_jpeg_is_400(client: AsyncClient):
    """Битый JPEG: 400, не 500."""
    r = await client.post(
        "/infer",
        files={"file": ("bad.jpg", b"not-a-real-jpeg-bytes", "image/jpeg")},
    )
    assert r.status_code == 400
    assert "декодировать" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_infer_oversize_is_413(client: AsyncClient):
    # Формируем 16 МБ «изображения» (детектор падает раньше, чем читает всё).
    big = b"\xff\xd8\xff\xe0" + b"\x00" * (16 * 1024 * 1024)
    r = await client.post(
        "/infer",
        files={"file": ("big.jpg", big, "image/jpeg")},
    )
    # 413 предпочтительнее, но 400 (если PIL упал на verify) тоже ок —
    # оба варианта лучше 500.
    assert r.status_code in (400, 413)


@pytest.mark.asyncio
async def test_infer_with_no_detections():
    """Детектор без mock_detections: count=0, detections=[]."""
    from httpx import ASGITransport, AsyncClient

    from app.detectors.mock import MockDetector, make_test_jpeg
    from app.main import app

    app.state.detector = MockDetector(fixed_detections=[])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/infer",
            files={"file": ("test.jpg", make_test_jpeg(), "image/jpeg")},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["detections"] == []


# ---------- unit: factories ----------


def test_build_detector_coco(monkeypatch):
    monkeypatch.setenv("DETECTOR", "coco")
    monkeypatch.setenv("DEVICE", "cpu")
    from app.config import get_settings
    from app.factory import build_detector

    get_settings.cache_clear()
    det = build_detector(get_settings())
    assert det.name == "yolov8-coco"


def test_build_detector_defect_stub(monkeypatch):
    monkeypatch.setenv("DETECTOR", "defect")
    from app.config import get_settings
    from app.factory import build_detector

    get_settings.cache_clear()
    det = build_detector(get_settings())
    assert det.name == "defect-stub"


def test_build_detector_unknown_raises(monkeypatch):
    monkeypatch.setenv("DETECTOR", "nope")
    from pydantic import ValidationError

    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValidationError) as exc_info:
        get_settings()
    # pydantic v2 формулирует ошибку по полю detector
    assert "detector" in str(exc_info.value)
