"""Обучение YOLOv8n на синтетических дефектах (corrosion/leak/damage).

Запуск:
    python scripts/yolo_train.py                 # дефолты
    python scripts/yolo_train.py --epochs 50     # больше эпох
    python scripts/yolo_train.py --resume        # продолжить с last.pt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "dataset" / "data.yaml"
DEFAULT_OUT = ROOT / "models"


def main() -> int:
    parser = argparse.ArgumentParser(description="Train YOLOv8n on synthetic defects")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="path to data.yaml")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output dir for weights")
    parser.add_argument("--model", default="yolov8n.pt", help="base model (default: yolov8n.pt)")
    parser.add_argument("--epochs", type=int, default=30, help="number of epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="image size")
    parser.add_argument("--batch", type=int, default=8, help="batch size (CPU-friendly)")
    parser.add_argument("--workers", type=int, default=2, help="dataloader workers")
    parser.add_argument("--device", default="cpu", help="cuda device, i.e. 0 or 0,1,2,3 or cpu")
    parser.add_argument("--name", default="defect_yolov8n_v1", help="run name")
    parser.add_argument("--resume", action="store_true", help="resume from last.pt in out/name")
    args = parser.parse_args()

    if not args.data.exists():
        print(f"ERROR: data.yaml not found: {args.data}", file=sys.stderr)
        print("  Сначала сгенерируйте датасет: python scripts/synth_train_data.py", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO  # тяжёлый импорт — только если реально тренируем

    model = YOLO(args.model)
    print(f"[yolo_train] data={args.data} epochs={args.epochs} imgsz={args.imgsz} device={args.device}")
    results = model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=args.device,
        project=str(args.out),
        name=args.name,
        exist_ok=True,
        resume=args.resume,
        verbose=True,
        seed=42,
        patience=10,  # early stop, если val mAP не растёт 10 эпох
    )

    best = args.out / args.name / "weights" / "best.pt"
    last = args.out / args.name / "weights" / "last.pt"
    print(f"[yolo_train] done. best={best} exists={best.exists()} last={last} exists={last.exists()}")
    return 0 if best.exists() else 2


if __name__ == "__main__":
    raise SystemExit(main())
