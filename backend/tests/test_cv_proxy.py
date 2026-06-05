"""Тесты CV-прокси роутера: успех, 401, 4xx, 5xx, невалидные файлы."""
from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from PIL import Image

from app.services.cv_client import CVBadImageError, CVUnavailableError


def _make_jpeg_bytes() -> bytes:
    """Минимальный валидный JPEG для тестов (1x1 белый пиксель)."""
    img = Image.new("RGB", (1, 1), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class _FakeCVClient:
    """Подделка CVClient с поддержкой async context manager."""

    def __init__(self, json_response=None, raises: Exception | None = None):
        self._json = json_response
        self._raises = raises

    async def __aenter__(self) -> "_FakeCVClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def infer(self, *_a, **_kw) -> dict:
        if self._raises is not None:
            raise self._raises
        return self._json or {"detector": "coco", "count": 0, "detections": []}

    async def health(self) -> bool:
        return self._raises is None


def _patch_cv(json_response=None, raises: Exception | None = None):
    return patch(
        "app.api.v1.cv.get_cv_client",
        lambda: _FakeCVClient(json_response=json_response, raises=raises),
    )


# ---------- POST /cv/infer ----------


@pytest.mark.asyncio
async def test_infer_requires_auth(client):
    r = await client.post(
        "/api/v1/cv/infer",
        files={"file": ("p.jpg", _make_jpeg_bytes(), "image/jpeg")},
    )
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_infer_empty_file_400(client, manager_token):
    r = await client.post(
        "/api/v1/cv/infer",
        files={"file": ("p.jpg", b"", "image/jpeg")},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert r.status_code == 400
    assert "Пустой" in r.json()["detail"]


@pytest.mark.asyncio
async def test_infer_oversize_413(client, manager_token):
    big = b"\x00" * (15 * 1024 * 1024 + 1)
    r = await client.post(
        "/api/v1/cv/infer",
        files={"file": ("p.jpg", big, "image/jpeg")},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_infer_success_passes_through(client, manager_token):
    expected = {
        "detector": "yolov8-coco",
        "count": 1,
        "latency_ms": 12.3,
        "image_size": {"width": 1, "height": 1},
        "detections": [
            {
                "label": "person",
                "confidence": 0.9,
                "bbox": {"x_min": 0, "y_min": 0, "x_max": 1, "y_max": 1},
                "detector": "yolov8-coco",
                "meta": {},
            }
        ],
    }
    with _patch_cv(json_response=expected):
        r = await client.post(
            "/api/v1/cv/infer",
            files={"file": ("p.jpg", _make_jpeg_bytes(), "image/jpeg")},
            headers={"Authorization": f"Bearer {manager_token}"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["detector"] == "yolov8-coco"
    assert body["count"] == 1
    assert body["detections"][0]["label"] == "person"


@pytest.mark.asyncio
async def test_infer_bad_image_400(client, manager_token):
    with _patch_cv(raises=CVBadImageError("Не удалось декодировать")):
        r = await client.post(
            "/api/v1/cv/infer",
            files={"file": ("p.jpg", b"junk", "image/jpeg")},
            headers={"Authorization": f"Bearer {manager_token}"},
        )
    assert r.status_code == 400
    assert "декодировать" in r.json()["detail"]


@pytest.mark.asyncio
async def test_infer_unavailable_503(client, manager_token):
    with _patch_cv(raises=CVUnavailableError("connection refused")):
        r = await client.post(
            "/api/v1/cv/infer",
            files={"file": ("p.jpg", _make_jpeg_bytes(), "image/jpeg")},
            headers={"Authorization": f"Bearer {manager_token}"},
        )
    assert r.status_code == 503
    assert "недоступен" in r.json()["detail"]


# ---------- GET /cv/detectors ----------


@pytest.mark.asyncio
async def test_detectors_requires_auth(client):
    r = await client.get("/api/v1/cv/detectors")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_detectors_returns_supported_list_when_unavailable(client, manager_token):
    """Если CV-сервис лежит — UI должен получить хоть что-то, а не 500."""
    with _patch_cv(raises=CVUnavailableError("nope")):
        r = await client.get(
            "/api/v1/cv/detectors",
            headers={"Authorization": f"Bearer {manager_token}"},
        )
    assert r.status_code == 200
    body = r.json()
    assert "coco" in body["supported"]
    assert body.get("available") is False
