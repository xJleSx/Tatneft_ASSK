"""Генератор синтетических изображений для проверки CV-пайплайна.

Что рисуем:
- 'person': стилизованный человечек (голова + тело + конечности).
- 'car': прямоугольник с колёсами (вид сбоку).
- 'fire_hydrant': вертикальный красный цилиндр с шапкой.

YOLO (COCO) обучен на реальных фото, поэтому стилизованные рисунки
могут НЕ детектироваться. Цель скрипта — проверить, что pipeline
ultralytics загружается и inference выполняется (даже если detections=[]).

Для уверенной детекции синтетики — нужно обучать модель на своих
примерах (см. README, раздел "Что нужно для следующего шага").
"""
from __future__ import annotations

import io
import random
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter

SceneKind = Literal["person", "car", "fire_hydrant", "multi", "noise", "real_photo"]


@dataclass(slots=True)
class SyntheticScene:
    kind: SceneKind
    image_bytes: bytes
    image_size: tuple[int, int]
    expected_label: str | None  # что МОЖЕТ найти YOLO (best-effort, не гарантия)


def _to_jpeg_bytes(img: Image.Image, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    # RGB обязательно для JPEG (PIL бросит RGBA -> JPEG)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _gradient_bg(size: tuple[int, int], top: tuple[int, int, int], bot: tuple[int, int, int]) -> Image.Image:
    """Простой вертикальный градиент — 'небо' / 'земля'."""
    w, h = size
    img = Image.new("RGB", size, top)
    px = img.load()
    assert px is not None
    for y in range(h):
        ratio = y / max(1, h - 1)
        c = tuple(int(top[i] * (1 - ratio) + bot[i] * ratio) for i in range(3))
        for x in range(0, w, 4):  # шаг 4 = быстрее
            px[x, y] = c
    return img


# ---------- Примитивы ----------


def _draw_person(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float = 1.0) -> None:
    """Стик-человечек, отцентрированный в (cx, cy) — это точка 'головы'."""
    head_r = int(15 * scale)
    body_h = int(60 * scale)
    arm_w = int(40 * scale)
    leg_h = int(60 * scale)
    line_w = max(2, int(4 * scale))

    # Голова
    draw.ellipse([cx - head_r, cy - head_r, cx + head_r, cy + head_r], fill=(255, 220, 180), outline="black", width=line_w)
    # Тело
    body_top = cy + head_r
    body_bot = body_top + body_h
    draw.line([cx, body_top, cx, body_bot], fill="black", width=line_w)
    # Руки
    draw.line([cx - arm_w, body_top + 10 * scale, cx + arm_w, body_top + 10 * scale], fill="black", width=line_w)
    # Ноги
    draw.line([cx, body_bot, cx - 25 * scale, body_bot + leg_h], fill="black", width=line_w)
    draw.line([cx, body_bot, cx + 25 * scale, body_bot + leg_h], fill="black", width=line_w)


def _draw_car(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float = 1.0) -> None:
    """Машинка-вид-сбоку: прямоугольник + 2 колеса."""
    w = int(200 * scale)
    h = int(80 * scale)
    body = [cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2]
    draw.rectangle(body, fill=(180, 30, 30), outline="black", width=max(2, int(3 * scale)))
    # Кабина (верх)
    cab_w = int(110 * scale)
    cab_h = int(40 * scale)
    cab = [cx - cab_w // 2, cy - h // 2 - cab_h, cx + cab_w // 2, cy - h // 2 + 5 * scale]
    draw.rectangle(cab, fill=(220, 60, 60), outline="black", width=max(2, int(3 * scale)))
    # Колёса
    wheel_r = int(20 * scale)
    for offset in (-int(60 * scale), int(60 * scale)):
        draw.ellipse(
            [cx + offset - wheel_r, cy + h // 2 - wheel_r, cx + offset + wheel_r, cy + h // 2 + wheel_r],
            fill="black",
        )
        draw.ellipse(
            [cx + offset - wheel_r // 2, cy + h // 2 - wheel_r // 2, cx + offset + wheel_r // 2, cy + h // 2 + wheel_r // 2],
            fill="gray",
        )


def _draw_hydrant(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float = 1.0) -> None:
    """Пожарный гидрант: красная 'бочка' + шапка + ножка."""
    body_w = int(40 * scale)
    body_h = int(70 * scale)
    body = [cx - body_w // 2, cy - body_h // 2, cx + body_w // 2, cy + body_h // 2]
    draw.rectangle(body, fill=(220, 30, 30), outline="black", width=max(2, int(3 * scale)))
    # Шапка
    cap_h = int(20 * scale)
    draw.rectangle(
        [cx - body_w // 2 - 5 * scale, cy - body_h // 2 - cap_h, cx + body_w // 2 + 5 * scale, cy - body_h // 2],
        fill=(200, 30, 30),
        outline="black",
        width=max(2, int(3 * scale)),
    )
    # Ножка
    base_h = int(10 * scale)
    draw.rectangle(
        [cx - body_w // 2, cy + body_h // 2, cx + body_w // 2, cy + body_h // 2 + base_h],
        fill="black",
    )
    # Боковые 'уши'
    for sign in (-1, 1):
        x0 = cx + sign * (body_w // 2 + 8 * scale)
        x1 = x0 + sign * int(15 * scale)
        if x1 < x0:
            x0, x1 = x1, x0
        draw.rectangle(
            [x0, cy - 5 * scale, x1, cy + 15 * scale],
            fill=(220, 30, 30),
            outline="black",
            width=max(1, int(2 * scale)),
        )


# ---------- Сцены ----------


def make_person_scene(
    size: tuple[int, int] = (640, 480), seed: int | None = 42
) -> SyntheticScene:
    """Один человек по центру на фоне градиента неба."""
    rng = random.Random(seed)
    img = _gradient_bg(size, top=(135, 206, 235), bot=(200, 220, 200))
    draw = ImageDraw.Draw(img)
    cx, cy = size[0] // 2, int(size[1] * 0.35)
    scale = rng.uniform(1.2, 2.0)
    _draw_person(draw, cx, cy, scale=scale)
    # Лёгкий шум — YOLO лучше реагирует на не-идеальные изображения
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    return SyntheticScene(
        kind="person", image_bytes=_to_jpeg_bytes(img), image_size=size, expected_label="person"
    )


def make_car_scene(size: tuple[int, int] = (640, 480), seed: int | None = 42) -> SyntheticScene:
    img = _gradient_bg(size, top=(135, 206, 235), bot=(180, 180, 180))
    draw = ImageDraw.Draw(img)
    cx, cy = size[0] // 2, int(size[1] * 0.65)
    _draw_car(draw, cx, cy, scale=2.0)
    return SyntheticScene(
        kind="car", image_bytes=_to_jpeg_bytes(img), image_size=size, expected_label="car"
    )


def make_hydrant_scene(size: tuple[int, int] = (640, 480), seed: int | None = 42) -> SyntheticScene:
    img = _gradient_bg(size, top=(200, 200, 200), bot=(120, 100, 90))
    draw = ImageDraw.Draw(img)
    cx, cy = size[0] // 2, size[1] // 2
    _draw_hydrant(draw, cx, cy, scale=2.5)
    return SyntheticScene(
        kind="fire_hydrant",
        image_bytes=_to_jpeg_bytes(img),
        image_size=size,
        expected_label="fire_hydrant",
    )


def make_multi_scene(
    size: tuple[int, int] = (1280, 720), seed: int | None = 42
) -> SyntheticScene:
    """Несколько объектов разных типов на одной сцене."""
    rng = random.Random(seed)
    img = _gradient_bg(size, top=(135, 206, 235), bot=(190, 190, 170))
    draw = ImageDraw.Draw(img)
    # 2 человека
    for x_frac in (0.25, 0.75):
        _draw_person(draw, int(size[0] * x_frac), int(size[1] * 0.40), scale=rng.uniform(1.4, 1.8))
    # 1 машина
    _draw_car(draw, int(size[0] * 0.5), int(size[1] * 0.78), scale=2.5)
    return SyntheticScene(
        kind="multi", image_bytes=_to_jpeg_bytes(img), image_size=size, expected_label=None
    )


def make_noise_scene(size: tuple[int, int] = (640, 480), seed: int | None = 42) -> SyntheticScene:
    """Просто RGB-шум — гарантированный detections=[] (и проверка, что детектор не падает)."""
    rng = random.Random(seed)
    img = Image.new("RGB", size)
    px = img.load()
    assert px is not None  # для mypy (load() может вернуть None на некоторых режимах)
    for y in range(size[1]):
        for x in range(size[0]):
            px[x, y] = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
    return SyntheticScene(
        kind="noise", image_bytes=_to_jpeg_bytes(img), image_size=size, expected_label=None
    )


def make_real_photo_scene() -> SyntheticScene:
    """Реальное фото из tests/fixtures/sample_person.jpg (если есть).

    Скачивается скриптом scripts/fetch_sample_image.py. В отличие от
    стилизованных сцен, YOLOv8 (COCO) находит на нём объекты с высокой
    уверенностью — это и есть «работающая детекция» для демо.
    """
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parent.parent
        / "tests"
        / "fixtures"
        / "sample_person.jpg"
    )
    if not fixture.exists():
        raise FileNotFoundError(
            f"{fixture} не найден. Скачай: python scripts/fetch_sample_image.py"
        )
    data = fixture.read_bytes()
    with Image.open(fixture) as img:
        size = img.size
    return SyntheticScene(
        kind="real_photo",
        image_bytes=data,
        image_size=size,
        expected_label="person",  # pexels 220453 — портрет
    )


# ---------- Универсальный билдер ----------


def build_scene(kind: SceneKind = "multi", **kwargs) -> SyntheticScene:
    if kind == "person":
        return make_person_scene(**kwargs)
    if kind == "car":
        return make_car_scene(**kwargs)
    if kind == "fire_hydrant":
        return make_hydrant_scene(**kwargs)
    if kind == "multi":
        return make_multi_scene(**kwargs)
    if kind == "noise":
        return make_noise_scene(**kwargs)
    if kind == "real_photo":
        return make_real_photo_scene()
    raise ValueError(f"Unknown scene: {kind!r}")


def build_all_scenes(**kwargs) -> list[SyntheticScene]:
    kinds: tuple[SceneKind, ...] = (
        "person", "car", "fire_hydrant", "multi", "noise", "real_photo"
    )
    return [build_scene(k, **kwargs) for k in kinds]
