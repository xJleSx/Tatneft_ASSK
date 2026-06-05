"""conftest: фикстуры для тестов CV-сервиса.

Тесты, требующие torch/ultralytics/веса, пропускаются если их нет.
Без torch тестируем только /health и статические части /detectors.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Прячем DETECTOR от .env, чтобы Settings() не падал на чём-то неожиданном.
os.environ.setdefault("APP_ENV", "dev")


def _has_torch() -> bool:
    try:
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
        return True
    except ImportError:
        return False


def _has_weights() -> bool:
    from app.config import DEFAULT_DEFECT_WEIGHTS

    return Path(DEFAULT_DEFECT_WEIGHTS).is_file()


needs_torch = pytest.mark.skipif(
    not _has_torch(),
    reason="torch/ultralytics не установлены",
)


needs_weights = pytest.mark.skipif(
    not _has_weights(),
    reason=f"Нет весов дефектов: {Path(__file__).parent.parent / 'weights' / 'defect.pt'}",
)
