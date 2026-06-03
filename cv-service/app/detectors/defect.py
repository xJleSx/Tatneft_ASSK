"""Заглушка детектора дефектов.

В MVP готовых весов под нефтегаз нет. Этот класс:
- не падает и не требует GPU/torch;
- возвращает пустой список + явный флаг `model_loaded=False` в meta
  при warmup(), чтобы caller видел, что сервис работает, но модель
  не обучена.

Контракт НЕ меняется: когда появится обученная модель, DefectDetector
просто получает ту же реализацию, что CocoDetector (YOLO.predict), но
со своими весами и списком классов (rust, leak, corrosion_severe, ...).
"""

from __future__ import annotations

import io
import logging

from PIL import Image

from app.detectors.base import BaseDetector, Detection

log = logging.getLogger(__name__)


class DefectDetector(BaseDetector):
    """Заглушка. Вернёт пустой список + meta с явным статусом.

    Используется в dev/staging до появления обученной модели.
    """

    name = "defect-stub"

    def __init__(self) -> None:
        self._model_loaded = False

    def warmup(self) -> None:
        # Проверяем, что Pillow читает наш фиктивный байтовый поток — этого
        # достаточно, чтобы детектор не падал при первом detect().
        try:
            Image.new("RGB", (8, 8), color=(0, 0, 0))
        except Exception as e:
            log.error("Pillow not available: %s", e)
            raise
        self._model_loaded = False
        log.warning(
            "DefectDetector работает в режиме STUB. "
            "Обученная модель не загружена. detect() вернёт []."
        )

    def detect(self, image_bytes: bytes) -> list[Detection]:
        # Проверяем только валидность изображения — это нужно, чтобы
        # CV-сервис отвечал 400 на битый JPEG, а не 500.
        try:
            Image.open(io.BytesIO(image_bytes)).verify()
        except Exception as e:
            raise ValueError(f"Не удалось декодировать изображение: {e}") from e
        return []  # ничего не находим, пока не будет обученной модели
