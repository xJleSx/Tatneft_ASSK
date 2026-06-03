"""Генератор синтетического датасета дефектов оборудования для YOLOv8.

3 класса:
  0 - corrosion  (оранжево-коричневое пятно неправильной формы)
  1 - leak       (тёмная вертикальная полоса + мокрое пятно внизу)
  2 - damage     (чёрная царапина/трещина)

Выход — YOLO-формат:
  dataset/
    images/train/  *.jpg
    images/val/    *.jpg
    labels/train/  *.txt  (каждая строка: cls xc yc w h, нормализованные 0..1)
    labels/val/    *.txt
    data.yaml      (YOLO-конфиг)

Запуск:
    python scripts/synth_train_data.py                       # 400 train + 100 val
    python scripts/synth_train_data.py --count 800 --val 200  # больше
    python scripts/synth_train_data.py --out dataset_v2      # другая папка
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

CLASSES: tuple[str, ...] = ("corrosion", "leak", "damage")
IMG_SIZE = 640  # квадрат, как YOLO imgsz


@dataclass(slots=True)
class Box:
    cls: int
    xc: float  # нормализованный центр
    yc: float
    w: float
    h: float

    def to_yolo_line(self) -> str:
        return f"{self.cls} {self.xc:.6f} {self.yc:.6f} {self.w:.6f} {self.h:.6f}"


# ---------- Фоны (numpy — в ~10x быстрее пиксельного PIL) ----------


def _metal_texture(
    size: int, rng: random.Random, np_rng: np.random.Generator, base: tuple[int, int, int]
) -> Image.Image:
    """Серый металл: диагональный градиент + RGB-шум + штрихи (PIL)."""
    arr = np.empty((size, size, 3), dtype=np.int16)
    # Диагональный градиент через numpy meshgrid (~20x быстрее цикла)
    ys, xs = np.indices((size, size), dtype=np.float32)
    t = (xs + ys) / (2 * size)
    shade = base[0] * (1 - t) + (base[0] - 20) * t  # (size, size)
    noise = np_rng.integers(-15, 16, size=(size, size, 3))
    arr[:, :, 0] = shade + noise[:, :, 0]
    arr[:, :, 1] = shade + noise[:, :, 1]
    arr[:, :, 2] = shade + noise[:, :, 2]
    np.clip(arr, 0, 255, out=arr)
    img = Image.fromarray(arr.astype(np.uint8), mode="RGB")

    # Тонкие штрихи (PIL draw — норм, всего 120 линий)
    draw = ImageDraw.Draw(img)
    for _ in range(120):
        x0, y0 = rng.randint(0, size), rng.randint(0, size)
        length = rng.randint(20, 80)
        angle = rng.uniform(0, math.pi)
        x1 = int(x0 + length * math.cos(angle))
        y1 = int(y0 + length * math.sin(angle))
        c = max(0, min(255, base[0] + rng.randint(-25, 25)))
        draw.line([x0, y0, x1, y1], fill=(c, c, c), width=1)
    return img


def make_background(
    rng: random.Random, np_rng: np.random.Generator, size: int = IMG_SIZE
) -> Image.Image:
    """Выбираем один из вариантов фона (3 металлических оттенка)."""
    palettes = [
        (165, 165, 170),  # светлый алюминий
        (110, 110, 115),  # тёмная сталь
        (140, 130, 120),  # оцинковка
    ]
    base = rng.choice(palettes)
    return _metal_texture(size, rng, np_rng, base)


# ---------- Дефекты ----------


def _draw_corrosion(
    draw: ImageDraw.ImageDraw,
    rng: random.Random,
    cx: int,
    cy: int,
    radius: int,
) -> tuple[int, int, int, int]:
    """Ржавчина: скопление эллипсов с рыжими/коричневыми оттенками.

    Возвращает bbox (x0, y0, x1, y1) в пикселях.
    """
    palette = [
        (180, 90, 30),
        (200, 110, 40),
        (150, 70, 25),
        (220, 130, 60),
        (130, 60, 20),
    ]
    blobs = rng.randint(5, 12)
    min_x = min_y = 10**9
    max_x = max_y = -1
    for _ in range(blobs):
        ox = cx + rng.randint(-radius // 2, radius // 2)
        oy = cy + rng.randint(-radius // 2, radius // 2)
        r = max(8, int(radius * rng.uniform(0.25, 0.55)))
        color = rng.choice(palette)
        draw.ellipse([ox - r, oy - r, ox + r, oy + r], fill=color)
        min_x = min(min_x, ox - r)
        min_y = min(min_y, oy - r)
        max_x = max(max_x, ox + r)
        max_y = max(max_y, oy + r)
    # Тёмный центр (имитация глубины коррозии)
    cr = max(10, int(radius * 0.3))
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(80, 40, 15))
    return min_x, min_y, max_x, max_y


def _draw_leak(
    draw: ImageDraw.ImageDraw,
    rng: random.Random,
    cx: int,
    cy: int,
    height: int,
) -> tuple[int, int, int, int]:
    """Утечка: тёмная вертикальная полоса + мокрое пятно внизу."""
    width = max(8, int(height * rng.uniform(0.06, 0.12)))
    x0 = cx - width // 2
    y0 = cy - height // 2
    x1 = cx + width // 2
    y1 = cy + height // 2
    # Основная полоса (градиент через серию прямоугольников)
    steps = max(8, height // 8)
    for i in range(steps):
        ty = y0 + int(i * height / steps)
        ratio = i / max(1, steps - 1)
        # Темнее сверху, чуть светлее внизу
        shade = int(20 + 30 * (1 - ratio) + rng.randint(-5, 5))
        draw.rectangle(
            [x0 + rng.randint(-1, 1), ty, x1 + rng.randint(-1, 1), ty + height // steps + 2],
            fill=(shade, shade, max(0, shade - 5)),
        )
    # Мокрое пятно внизу
    spot_r = max(20, int(width * rng.uniform(2.0, 3.5)))
    draw.ellipse(
        [cx - spot_r, y1 - spot_r // 2, cx + spot_r, y1 + spot_r // 2],
        fill=(30, 30, 35),
    )
    # Блик (мокрый блеск)
    draw.ellipse(
        [cx - spot_r // 3, y1 - spot_r // 3, cx + spot_r // 3, y1 - spot_r // 4],
        fill=(120, 120, 125),
    )
    return x0, y0, x1 + spot_r, y1 + spot_r // 2


def _draw_damage(
    draw: ImageDraw.ImageDraw,
    rng: random.Random,
    cx: int,
    cy: int,
    length: int,
) -> tuple[int, int, int, int]:
    """Повреждение: чёрная зигзагообразная царапина или трещина."""
    angle = rng.uniform(0, 2 * math.pi)
    dx = math.cos(angle) * length / 2
    dy = math.sin(angle) * length / 2
    x0, y0 = int(cx - dx), int(cy - dy)
    x1, y1 = int(cx + dx), int(cy + dy)
    points = [(x0, y0)]
    segments = rng.randint(4, 8)
    for i in range(1, segments):
        t = i / segments
        # Базовая точка на прямой
        bx = x0 + int((x1 - x0) * t)
        by = y0 + int((y1 - y0) * t)
        # Перпендикулярное смещение
        nx = -(y1 - y0) / length
        ny = (x1 - x0) / length
        amp = rng.randint(8, 25)
        offset = rng.randint(-amp, amp)
        points.append((bx + int(nx * offset), by + int(ny * offset)))
    points.append((x1, y1))
    width = rng.randint(2, 5)
    # Тёмная царапина
    for i in range(width):
        draw.line(points, fill=(15, 15, 15), width=width - i + 1)
    # Чуть светлая «тень» сбоку
    shadow = [(p[0] + 1, p[1] + 1) for p in points]
    draw.line(shadow, fill=(70, 70, 70), width=1)
    return (
        min(p[0] for p in points) - width,
        min(p[1] for p in points) - width,
        max(p[0] for p in points) + width,
        max(p[1] for p in points) + width,
    )


# ---------- Сборка изображения ----------


def _clamp_box(
    x0: int, y0: int, x1: int, y1: int, size: int
) -> tuple[int, int, int, int]:
    return (
        max(0, x0),
        max(0, y0),
        min(size, x1),
        min(size, y1),
    )


def _photo_effects(
    img: Image.Image, rng: random.Random, np_rng: np.random.Generator
) -> Image.Image:
    """Лёгкий блюр + шум (numpy) — чтобы YOLO не переобучался на идеальные пятна."""
    if rng.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.3, 1.2)))
    # Шум через numpy blend (~10x быстрее Image.effect_noise + Image.blend)
    if rng.random() < 0.7:
        arr = np.asarray(img, dtype=np.float32)
        noise = np_rng.integers(0, 256, size=arr.shape, dtype=np.int16).astype(np.float32)
        alpha = rng.uniform(0.05, 0.15)
        arr = arr * (1 - alpha) + noise * alpha
        np.clip(arr, 0, 255, out=arr)
        img = Image.fromarray(arr.astype(np.uint8), mode="RGB")
    return img


def make_sample(
    rng: random.Random, np_rng: np.random.Generator, size: int = IMG_SIZE
) -> tuple[Image.Image, list[Box]]:
    """Одна пара (image, labels)."""
    bg = make_background(rng, np_rng, size)
    draw = ImageDraw.Draw(bg)

    n_defects = rng.randint(1, 4)
    boxes: list[Box] = []
    for _ in range(n_defects):
        cls = rng.randint(0, len(CLASSES) - 1)
        # Размер зависит от класса
        if cls == 0:  # corrosion
            radius = rng.randint(35, 90)
            cx, cy = rng.randint(radius + 10, size - radius - 10), rng.randint(
                radius + 10, size - radius - 10
            )
            x0, y0, x1, y1 = _draw_corrosion(draw, rng, cx, cy, radius)
        elif cls == 1:  # leak
            height = rng.randint(120, 280)
            cx = rng.randint(40, size - 40)
            cy = rng.randint(height // 2 + 20, size - height // 2 - 20)
            x0, y0, x1, y1 = _draw_leak(draw, rng, cx, cy, height)
        else:  # damage
            length = rng.randint(80, 220)
            cx, cy = rng.randint(60, size - 60), rng.randint(60, size - 60)
            x0, y0, x1, y1 = _draw_damage(draw, rng, cx, cy, length)

        x0, y0, x1, y1 = _clamp_box(x0, y0, x1, y1, size)
        if x1 <= x0 or y1 <= y0:
            continue
        # YOLO: xc, yc, w, h — нормализованные [0..1]
        xc = (x0 + x1) / 2 / size
        yc = (y0 + y1) / 2 / size
        w = (x1 - x0) / size
        h = (y1 - y0) / size
        boxes.append(Box(cls=cls, xc=xc, yc=yc, w=w, h=h))

    bg = _photo_effects(bg, rng, np_rng)
    return bg, boxes


# ---------- Сохранение ----------


def _save_sample(
    img: Image.Image,
    boxes: list[Box],
    out_dir: Path,
    split: str,
    idx: int,
    rng: random.Random,
) -> None:
    img_dir = out_dir / "images" / split
    lbl_dir = out_dir / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    name = f"{split}_{idx:04d}"
    img_path = img_dir / f"{name}.jpg"
    img.save(img_path, format="JPEG", quality=rng.randint(70, 92))

    lbl_path = lbl_dir / f"{name}.txt"
    lbl_path.write_text(
        "\n".join(b.to_yolo_line() for b in boxes) + ("\n" if boxes else ""),
        encoding="utf-8",
    )


def _write_data_yaml(out_dir: Path) -> None:
    yaml = (
        f"# YOLO data config (synthetic defects)\n"
        f"path: {out_dir.resolve()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"nc: {len(CLASSES)}\n"
        f"names: {list(CLASSES)}\n"
    )
    (out_dir / "data.yaml").write_text(yaml, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="dataset", help="Output directory")
    p.add_argument("--count", type=int, default=400, help="Number of train images")
    p.add_argument("--val", type=int, default=100, help="Number of val images")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--size", type=int, default=IMG_SIZE)
    args = p.parse_args(argv)

    out_dir = Path(args.out)
    # Если уже сгенерировано — перегенерим (быстро с numpy)
    if (out_dir / "data.yaml").exists():
        import shutil

        log_warn = lambda m: print(f"[warn] {m}", flush=True)  # noqa: E731
        log_warn(f"{out_dir} уже существует, удаляю и перегенерирую")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    np_rng = np.random.default_rng(args.seed)
    # Связка: rng и np_rng используют один seed → детерминированно.
    log = lambda msg: print(msg, flush=True)  # noqa: E731

    log(f"Генерация {args.count} train + {args.val} val в {out_dir.resolve()}")
    log(f"Классы: {CLASSES}")

    for split, n in (("train", args.count), ("val", args.val)):
        for i in range(n):
            img, boxes = make_sample(rng, np_rng, args.size)
            _save_sample(img, boxes, out_dir, split, i, rng)
            if (i + 1) % 100 == 0:
                log(f"  {split}: {i + 1}/{n}")
    _write_data_yaml(out_dir)
    log(f"Готово. data.yaml: {out_dir / 'data.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
