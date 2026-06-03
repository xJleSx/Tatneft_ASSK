"""Тесты CV-клиента: успех, 4xx, 5xx, network error."""
from __future__ import annotations

import httpx
import pytest

from app.services.cv_client import CVBadImageError, CVClient, CVUnavailableError, get_cv_client


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, handler):
        self._handler = handler
        self.calls: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return await self._handler(request)


def _build_client(handler) -> tuple[CVClient, _MockTransport]:
    transport = _MockTransport(handler)
    cv = CVClient(base_url="http://cv:8000", timeout_s=1.0)
    cv._client = httpx.AsyncClient(base_url="http://cv:8000", transport=transport)
    return cv, transport


@pytest.mark.asyncio
async def test_infer_success():
    async def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "detector": "yolov8-coco",
                "count": 1,
                "latency_ms": 12.3,
                "image_size": {"width": 640, "height": 480},
                "detections": [
                    {
                        "label": "person",
                        "confidence": 0.9,
                        "bbox": {"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100},
                        "detector": "yolov8-coco",
                        "meta": {"coco_class_id": 0},
                    }
                ],
            },
        )

    cv, transport = _build_client(handler)
    out = await cv.infer(b"\xff\xd8\xff\xe0test", filename="p.jpg")
    assert out["detector"] == "yolov8-coco"
    assert out["count"] == 1
    assert out["detections"][0]["label"] == "person"
    assert transport.calls[0].method == "POST"
    assert str(transport.calls[0].url).endswith("/infer")
    await cv._client.aclose()


@pytest.mark.asyncio
async def test_infer_4xx_is_bad_image():
    async def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Не удалось декодировать изображение")

    cv, _ = _build_client(handler)
    with pytest.raises(CVBadImageError):
        await cv.infer(b"junk", filename="p.jpg")
    await cv._client.aclose()


@pytest.mark.asyncio
async def test_infer_5xx_is_unavailable():
    async def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="model not loaded")

    cv, _ = _build_client(handler)
    with pytest.raises(CVUnavailableError):
        await cv.infer(b"\xff\xd8\xff\xe0", filename="p.jpg")
    await cv._client.aclose()


@pytest.mark.asyncio
async def test_infer_empty_input():
    """Пустые байты — CVBadImageError без обращения к сервису."""
    cv, transport = _build_client(lambda _r: httpx.Response(200, json={}))
    with pytest.raises(CVBadImageError, match="Пустой"):
        await cv.infer(b"", filename="p.jpg")
    assert transport.calls == []
    await cv._client.aclose()


@pytest.mark.asyncio
async def test_infer_network_error_is_unavailable():
    async def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    cv, _ = _build_client(handler)
    with pytest.raises(CVUnavailableError):
        await cv.infer(b"\xff\xd8\xff\xe0", filename="p.jpg")
    await cv._client.aclose()


@pytest.mark.asyncio
async def test_health():
    async def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "version": "0.1.0"})

    cv, _ = _build_client(handler)
    assert await cv.health() is True
    await cv._client.aclose()


@pytest.mark.asyncio
async def test_health_unreachable():
    async def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    cv, _ = _build_client(handler)
    assert await cv.health() is False
    await cv._client.aclose()


def test_get_cv_client_reads_settings():
    """get_cv_client строит клиент по Settings.cv_service_url."""
    cv = get_cv_client()
    assert cv._base_url.endswith(":8000")
    assert cv._timeout > 0
