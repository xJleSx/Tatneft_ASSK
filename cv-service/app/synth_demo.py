"""Демо-скрипт: генерим синтетику и гоним через CV-сервис / напрямую через CocoDetector.

Использование:
    python -m app.synth_demo                       # локально, через детектор в памяти
    python -m app.synth_demo --url http://localhost:8001   # через HTTP CV-сервис
    python -m app.synth_demo --kind all            # все сцены
    python -m app.synth_demo --kind person         # только person
    python -m app.synth_demo --no-save             # не сохранять PNG
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
import time
from pathlib import Path

from app.synth import build_scene

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("synth-demo")


def _save_image(scene_bytes: bytes, kind: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"synth_{kind}.jpg"
    path.write_bytes(scene_bytes)
    return path


def _run_via_http(url: str, scene_bytes: bytes) -> dict:
    import httpx

    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"{url.rstrip('/')}/infer",
            files={"file": ("synth.jpg", scene_bytes, "image/jpeg")},
        )
        r.raise_for_status()
        return r.json()


def _run_in_process(scene_bytes: bytes, conf: float = 0.25) -> dict:
    """Прогон через CocoDetector (без HTTP)."""
    from app.detectors.coco import CocoDetector

    det = CocoDetector(model_path=None, device="cpu", conf=conf, iou=0.45)
    det.warmup()
    t0 = time.perf_counter()
    detections = det.detect(scene_bytes)
    latency_ms = (time.perf_counter() - t0) * 1000
    return {
        "detector": det.name,
        "count": len(detections),
        "latency_ms": round(latency_ms, 2),
        "detections": [d.to_dict() for d in detections],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Synthetic detection demo")
    p.add_argument("--url", default=None, help="CV-service URL (если не задан — in-process)")
    p.add_argument(
        "--kind",
        default="all",
        choices=["all", "person", "car", "fire_hydrant", "multi", "noise", "real_photo"],
    )
    p.add_argument("--no-save", action="store_true", help="Не сохранять PNG/JPEG в /tmp")
    p.add_argument("--conf", type=float, default=0.25, help="YOLO confidence threshold")
    args = p.parse_args(argv)

    if args.url:
        log.info("Mode: HTTP -> %s", args.url)
    else:
        log.info("Mode: in-process (CocoDetector)")

    kinds = (
        ["person", "car", "fire_hydrant", "multi", "noise", "real_photo"]
        if args.kind == "all"
        else [args.kind]
    )
    out_dir = Path(tempfile.gettempdir()) / "askk-cv-demo"
    if not args.no_save:
        log.info("Изображения сохраняются в: %s", out_dir)

    summary: list[dict] = []
    for kind in kinds:
        scene = build_scene(kind)  # type: ignore[arg-type]
        if not args.no_save:
            saved = _save_image(scene.image_bytes, kind, out_dir)
            log.info("[%s] scene saved: %s (%d bytes)", kind, saved, len(scene.image_bytes))

        try:
            if args.url:
                result = _run_via_http(args.url, scene.image_bytes)
            else:
                result = _run_in_process(scene.image_bytes, conf=args.conf)
        except Exception as e:
            log.error("[%s] inference failed: %s", kind, e)
            summary.append({"kind": kind, "error": str(e)})
            continue

        labels = [d["label"] for d in result.get("detections", [])]
        log.info(
            "[%s] detector=%s, count=%d, latency=%.1fms, labels=%s",
            kind,
            result.get("detector"),
            result.get("count", 0),
            result.get("latency_ms", 0.0),
            labels,
        )
        summary.append(
            {
                "kind": kind,
                "expected": scene.expected_label,
                "detector": result.get("detector"),
                "count": result.get("count", 0),
                "latency_ms": result.get("latency_ms", 0.0),
                "labels": labels,
            }
        )

    print()
    print("=" * 70)
    print("СВОДКА:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("=" * 70)

    if not args.url:
        log.info("Чтобы дёрнуть HTTP-сервис, сначала подними его:")
        log.info("  make cv-dev          # в одном терминале")
        log.info("  python -m app.synth_demo --url http://localhost:8000  # в другом")
    return 0


if __name__ == "__main__":
    sys.exit(main())
