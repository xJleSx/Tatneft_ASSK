"""Mock-детектор для тестов: возвращает фиксированные боксы, не требует torch.

Используется в test_*.py чтобы прогонять /infer без тяжёлых зависимостей.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from app.detectors.base import BaseDetector, Detection


class MockDetector(BaseDetector):
    name = "mock"

    def __init__(self, fixed_detections: list[Detection] | None = None) -> None:
        self._detections = fixed_detections or []

    def warmup(self) -> None:
        return

    def detect(self, image_bytes: bytes) -> list[Detection]:
        # Валидируем картинку — иначе тест с битым JPEG прошёл бы молча.
        try:
            Image.open(io.BytesIO(image_bytes)).verify()
        except Exception as e:
            raise ValueError(f"Не удалось декодировать изображение: {e}") from e
        return list(self._detections)


def make_test_jpeg(size: tuple[int, int] = (640, 480), color: str = "red") -> bytes:
    """Сгенерировать минимальный JPEG для тестов инференса.

    Полезно, когда не хочется таскать с собой бинарные фикстуры.
    """
    img = Image.new("RGB", size, color=color)
    ImageDraw.Draw(img).text((10, 10), "test", fill="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()
