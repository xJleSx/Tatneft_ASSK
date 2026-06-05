"""CV proxy: прокси для CV-сервиса, чтобы фронтенд не ходил напрямую.

В docker-compose CV-сервис живёт отдельно (контейнер `cv`, порт 8000 внутри сети,
наружу проброшен 8001). Чтобы:
- не открывать CV-сервис в общий интернет с теми же правилами, что и API,
- держать единый auth-контур (JWT от API),
- иметь возможность подменить провайдера (mock для тестов, real YOLO для прод),

делаем тонкий прокси в API: /cv/detectors, /cv/infer.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.models.user import User
from app.services.cv_client import CVBadImageError, CVUnavailableError, get_cv_client

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cv", tags=["cv"])


_MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB, как в CV-сервисе


@router.get("/detectors")
async def list_detectors(_: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    """Какие детекторы доступны в CV-сервисе.

    Если CV-сервис недоступен — отдаём дефолтный список, чтобы UI не падал.
    """
    try:
        async with get_cv_client() as cv:
            r = await cv._client.get("/detectors")
            if r.status_code == 200:
                return r.json()
    except CVUnavailableError as e:
        log.warning("CV /detectors unavailable: %s", e)
    except Exception as e:  # noqa: BLE001
        log.warning("CV /detectors error: %s", e)

    return {
        "active": "unknown",
        "supported": ["coco", "defect", "mock"],
        "available": False,
    }


@router.post("/infer")
async def infer(
    file: Annotated[UploadFile, File(description="JPEG/PNG/WebP, до 15 МБ")],
    _: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Прогонить фото через активный детектор CV-сервиса.

    Прозрачно прокидывает multipart в CV-сервис и возвращает его JSON как есть.
    Тонкая прослойка для:
    - авторизации (только залогиненные пользователи);
    - валидации размера файла до похода в CV (экономим сеть);
    - нормализации ошибок (4xx/5xx → понятные HTTP-коды фронту).
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Пустой файл")
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(413, "Файл больше 15 МБ")

    try:
        async with get_cv_client() as cv:
            result = await cv.infer(raw, filename=file.filename or "photo.jpg")
    except CVBadImageError as e:
        raise HTTPException(400, str(e)) from e
    except CVUnavailableError as e:
        raise HTTPException(503, f"CV-сервис недоступен: {e}") from e

    return result
