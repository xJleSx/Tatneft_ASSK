"""HTTP-клиент CV-сервиса.

Используется из backend, когда нужно прогнать фото через детектор.
В MVP — синхронный вызов; позже можно вынести в background task.

Пример:
    from app.services.cv_client import get_cv_client
    async with get_cv_client() as cv:
        result = await cv.infer(photo_bytes, photo_id=...)
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)


class CVUnavailableError(RuntimeError):
    """CV-сервис недоступен (network, 5xx, timeout)."""


class CVBadImageError(ValueError):
    """CV-сервис отверг изображение (4xx)."""


class CVClient:
    """Тонкая обёртка над /infer CV-сервиса."""

    def __init__(self, base_url: str, timeout_s: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> CVClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health(self) -> bool:
        if self._client is None:
            raise RuntimeError("Use 'async with CVClient(...) as cv'")
        try:
            r = await self._client.get("/health")
            return r.status_code == 200
        except httpx.HTTPError as e:
            log.warning("CV health check failed: %s", e)
            return False

    async def infer(self, image_bytes: bytes, *, filename: str = "photo.jpg") -> dict[str, Any]:
        """Прогнать картинку через детектор. Возвращает JSON как есть.

        Raises:
            CVUnavailableError: CV-сервис недоступен (network / 5xx / timeout).
            CVBadImageError: 4xx — невалидное изображение или превышен размер.
        """
        if self._client is None:
            raise RuntimeError("Use 'async with CVClient(...) as cv'")
        if not image_bytes:
            raise CVBadImageError("Пустой файл")
        try:
            r = await self._client.post(
                "/infer",
                files={"file": (filename, image_bytes, "image/jpeg")},
            )
        except httpx.HTTPError as e:
            raise CVUnavailableError(f"CV service unreachable: {e}") from e

        if 500 <= r.status_code < 600:
            raise CVUnavailableError(f"CV service {r.status_code}: {r.text[:200]}")
        if 400 <= r.status_code < 500:
            raise CVBadImageError(f"CV rejected image: {r.status_code} {r.text[:200]}")
        return r.json()


def get_cv_client() -> CVClient:
    """Построить клиент по настройкам backend.

    base_url берётся из CV_SERVICE_URL; если не задан — http://cv:8000
    (имя сервиса в docker-compose).
    """
    settings = get_settings()
    base_url = getattr(settings, "cv_service_url", None) or "http://cv:8000"
    timeout = float(getattr(settings, "cv_timeout_s", 30.0))
    return CVClient(base_url=base_url, timeout_s=timeout)
