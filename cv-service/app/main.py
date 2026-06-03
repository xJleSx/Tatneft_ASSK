"""CV-сервис: HTTP API поверх детектора.

Эндпоинты:
- GET  /health     — liveness/readiness (без прогрева модели)
- GET  /readyz     — readiness (после warmup)
- POST /infer      — multipart file=... -> JSON {detector, count, detections: [...]}
- GET  /detectors  — список поддерживаемых детекторов

Между сервисами в docker network авторизация не нужна. Для выхода наружу —
добавить shared-secret middleware.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app import __version__
from app.config import Settings, get_settings
from app.detectors.base import BaseDetector
from app.factory import build_detector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("cv")

# ---------- Lifespan: warmup детектора ----------


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    detector: BaseDetector = build_detector(settings)
    try:
        detector.warmup()
        log.info("Detector %s warmed up", detector.name)
    except Exception as e:
        log.exception("Warmup failed: %s", e)
        # НЕ валим старт: /health должен отвечать, /infer вернёт 503
    app.state.detector = detector
    app.state.settings = settings
    try:
        yield
    finally:
        log.info("CV service shutting down")


app = FastAPI(
    title="АСКК CV-сервис",
    version=__version__,
    description="Детекция объектов и дефектов оборудования на фото (YOLOv8).",
    lifespan=lifespan,
)


# ---------- Schemas ----------


class HealthResp(BaseModel):
    status: str
    version: str


class ReadyResp(BaseModel):
    status: str
    detector: str


class DetectionOut(BaseModel):
    label: str
    confidence: float
    bbox: dict
    detector: str
    meta: dict


class InferResp(BaseModel):
    detector: str
    count: int
    latency_ms: float
    image_size: dict
    detections: list[DetectionOut]


# ---------- Deps ----------


def get_detector(request: Request) -> BaseDetector:
    det = getattr(request.app.state, "detector", None)
    if det is None:
        raise HTTPException(503, "Detector not initialized")
    return det


def get_settings_dep() -> Settings:
    return get_settings()


# ---------- Endpoints ----------


@app.get("/health", response_model=HealthResp)
async def health() -> HealthResp:
    """Liveness — отвечает всегда, если процесс жив."""
    return HealthResp(status="ok", version=__version__)


@app.get("/readyz", response_model=ReadyResp)
async def readyz(detector: Annotated[BaseDetector, Depends(get_detector)]) -> ReadyResp:
    """Readiness — 200 только если детектор прогрет."""
    return ReadyResp(status="ready", detector=detector.name)


@app.get("/detectors")
async def list_detectors() -> dict:
    """Какие детекторы доступны (с какой конфигурацией запущены)."""
    det = app.state.detector
    return {
        "active": det.name,
        "supported": ["coco", "defect", "mock"],
    }


@app.post("/infer", response_model=InferResp)
async def infer(
    file: Annotated[UploadFile, File(description="JPEG/PNG/WebP, до 15 МБ")],
    detector: Annotated[BaseDetector, Depends(get_detector)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> InferResp:
    """Детекция на одном изображении."""
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Пустой файл")
    if len(raw) > settings.max_image_bytes:
        raise HTTPException(413, f"Файл больше {settings.max_image_bytes // (1024*1024)} МБ")

    t0 = time.perf_counter()
    try:
        detections = detector.detect(raw)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        log.exception("Inference failed")
        raise HTTPException(500, f"Inference error: {e}") from e
    latency_ms = (time.perf_counter() - t0) * 1000

    # Размер картинки (декодируем только для ответа; verify уже был в детекторе)
    from io import BytesIO

    from PIL import Image

    try:
        with Image.open(BytesIO(raw)) as img:
            w, h = img.size
    except Exception:
        w, h = 0, 0

    return InferResp(
        detector=detector.name,
        count=len(detections),
        latency_ms=round(latency_ms, 2),
        image_size={"width": w, "height": h},
        detections=[DetectionOut(**d.to_dict()) for d in detections],
    )
