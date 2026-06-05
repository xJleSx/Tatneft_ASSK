"""Синтезатор параметров телеметрии для seed-данных.

Содержит детерминированный генератор псевдослучайных, но стабильных во
времени значений параметров оборудования. Используется ТОЛЬКО для
наполнения БД реалистичными числами, чтобы дашборд выглядел «живым».

Контракт и диапазоны взяты из публичных отраслевых источников
(см. `docs/analogs.md`).
"""
from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.equipment import EquipmentType

# Параметры и их «физические» диапазоны (на основе публичных аналогов
# для нефтегазового оборудования).
_PARAM_RANGES: dict[EquipmentType, dict[str, tuple[float, float, str]]] = {
    EquipmentType.UECN: {
        "P_buf": (5.0, 25.0, "атм"),
        "P_lin": (10.0, 40.0, "атм"),
        "P_intake": (40.0, 120.0, "атм"),
        "T_motor": (40.0, 130.0, "°C"),
        "I": (30.0, 90.0, "А"),
        "V_freq": (40.0, 60.0, "Гц"),
        "Q_liq": (20.0, 200.0, "м³/сут"),
    },
    EquipmentType.USHGN: {
        "P_buf": (2.0, 15.0, "атм"),
        "P_lin": (5.0, 25.0, "атм"),
        "Q_liq": (5.0, 80.0, "м³/сут"),
        "level_dynamic": (500.0, 2000.0, "м"),
        "strokes_per_min": (4.0, 12.0, "ход/мин"),
    },
    EquipmentType.WELLHEAD: {
        "P_buf": (1.0, 30.0, "атм"),
        "T_buf": (10.0, 80.0, "°C"),
        "P_obv": (0.5, 10.0, "атм"),
    },
    EquipmentType.PUMP_UNIT: {
        "P_buf": (1.0, 10.0, "атм"),
        "I": (10.0, 60.0, "А"),
        "strokes_per_min": (4.0, 12.0, "ход/мин"),
    },
    EquipmentType.SEPARATOR: {
        "P": (1.0, 6.0, "атм"),
        "T": (10.0, 60.0, "°C"),
        "level": (0.2, 0.8, "д.ед."),
    },
    EquipmentType.OTHER: {
        "value": (0.0, 100.0, "ед"),
    },
}


def stable_seed(equipment_id: UUID, dt: datetime) -> int:
    """Детерминированный seed от equipment_id + minute-bucket."""
    bucket = int(dt.timestamp()) // 60
    raw = f"{equipment_id}:{bucket}".encode()
    return int(hashlib.sha256(raw).hexdigest(), 16) % (2**32)


def generate_params(equipment_type: EquipmentType, seed: int) -> dict[str, float]:
    """Сгенерировать набор параметров в допустимом диапазоне с шумом ±2%."""
    rng = random.Random(seed)
    ranges = _PARAM_RANGES.get(equipment_type, _PARAM_RANGES[EquipmentType.OTHER])
    out: dict[str, float] = {}
    for name, (lo, hi, _unit) in ranges.items():
        base = rng.uniform(lo, hi)
        noise = base * rng.uniform(-0.02, 0.02)
        out[name] = round(max(lo, min(hi, base + noise)), 3)
    return out


def inject_anomalies(
    params: dict[str, float],
    multipliers: dict[str, float],
) -> dict[str, float]:
    """Применить аномальные множители к выбранным параметрам (для seed)."""
    out = dict(params)
    for k, mult in multipliers.items():
        if k in out:
            out[k] = round(out[k] * mult, 3)
    return out


__all__ = [
    "PARAM_RANGES",
    "stable_seed",
    "generate_params",
    "inject_anomalies",
]
