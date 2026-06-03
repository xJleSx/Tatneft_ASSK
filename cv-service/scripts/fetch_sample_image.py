"""Скачивает реальное фото для smoke-теста YOLOv8.

Один раз: сохраняет JPEG в tests/fixtures/sample_person.jpg.
Источник: Pexels CDN (CC0). Если сети нет — печатает инструкцию.

Использование:
    python scripts/fetch_sample_image.py
"""
from __future__ import annotations

import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_person.jpg"
FIXTURE.parent.mkdir(parents=True, exist_ok=True)


def fetch(url: str, timeout: float = 30.0) -> bytes:
    import httpx

    log = f"GET {url}"
    print(log, flush=True)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.content


def main() -> int:
    if FIXTURE.exists() and FIXTURE.stat().st_size > 1000:
        print(f"Already exists: {FIXTURE} ({FIXTURE.stat().st_size} bytes)")
        return 0

    # Публичные бесплатные фото с детектируемыми объектами.
    # Pexels CDN отдаёт JPEG напрямую.
    candidates = [
        # Человек на улице
        "https://images.pexels.com/photos/220453/pexels-photo-220453.jpeg?w=640",
        # Машина
        "https://images.pexels.com/photos/170811/pexels-photo-170811.jpeg?w=640",
        # Cat
        "https://images.pexels.com/photos/45201/kitty-cat-kitten-pet-45201.jpeg?w=640",
    ]

    for url in candidates:
        try:
            data = fetch(url)
            FIXTURE.write_bytes(data)
            print(f"Saved: {FIXTURE} ({len(data)} bytes)")
            return 0
        except Exception as e:  # noqa: BLE001
            print(f"Failed {url}: {e}", file=sys.stderr)
            continue

    print("Не удалось скачать ни одну картинку. Положите JPEG вручную в", FIXTURE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
