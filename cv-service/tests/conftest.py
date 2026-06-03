"""conftest: подменяем app.state.detector на MockDetector."""

from __future__ import annotations

import os

# До любых импортов app.* выставляем детектор=mock (без torch/ultralytics)
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("DETECTOR", "mock")

import pytest
from httpx import ASGITransport, AsyncClient

from app.detectors.base import Detection
from app.detectors.mock import MockDetector
from app.main import app


@pytest.fixture
def mock_detector() -> MockDetector:
    return MockDetector(
        fixed_detections=[
            Detection(
                label="test_object",
                confidence=0.91,
                x_min=10,
                y_min=20,
                x_max=110,
                y_max=120,
                detector="mock",
                meta={"source": "fixture"},
            )
        ]
    )


@pytest.fixture
async def client(mock_detector) -> AsyncClient:
    """AsyncClient с подменой детектора на MockDetector (без torch)."""
    app.state.detector = mock_detector
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    # Не очищаем app.state — следующий тест перезапишет.
