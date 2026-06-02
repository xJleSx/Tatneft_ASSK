"""Mock-адаптер АСУ ТП.

Генерирует реалистичные параметры на основе типа оборудования и псевдослучайного
"состояния". Используется пока нет доступа к реальной АСУ ТП.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.integrations.asutp.base import AsutpAdapter
from app.models.equipment import EquipmentType

log = get_logger(__name__)


# Параметры и их "физические" диапазоны (на основе публичных аналогов
# для нефтегазового оборудования)
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


def _stable_seed(equipment_id: UUID, dt: datetime) -> int:
    """Детерминированный seed от equipment_id + minute-bucket."""
    bucket = int(dt.timestamp()) // 60
    raw = f"{equipment_id}:{bucket}".encode()
    return int(hashlib.sha256(raw).hexdigest(), 16) % (2**32)


def _generate_params(equipment_type: EquipmentType, seed: int) -> dict[str, float]:
    """Генерирует набор параметров в допустимом диапазоне с шумом."""
    import random

    rng = random.Random(seed)
    ranges = _PARAM_RANGES.get(equipment_type, _PARAM_RANGES[EquipmentType.OTHER])
    out: dict[str, float] = {}
    for name, (lo, hi, _unit) in ranges.items():
        base = rng.uniform(lo, hi)
        # Слабый шум ±2%
        noise = base * rng.uniform(-0.02, 0.02)
        out[name] = round(max(lo, min(hi, base + noise)), 3)
    return out


class MockAsutpAdapter(AsutpAdapter):
    """Возвращает синтетические, но стабильные во времени данные."""

    async def get_snapshot(self, equipment_id: UUID, at: datetime | None = None) -> dict[str, Any]:
        at = at or datetime.now(UTC)
        # Тип оборудования в прототипе — дефолтный, т.к. не ходим в БД здесь.
        # Реальный адаптер будет получать тип из БД.
        eq_type = self._resolve_type(equipment_id)
        seed = _stable_seed(equipment_id, at)
        params = _generate_params(eq_type, seed)
        return {
            "equipment_id": str(equipment_id),
            "observed_at": at.isoformat(),
            "source": "mock",
            "params": params,
        }

    async def get_history(
        self,
        equipment_id: UUID,
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        eq_type = self._resolve_type(equipment_id)
        out: list[dict[str, Any]] = []
        cur = since
        step = timedelta(minutes=15)
        while cur <= until:
            seed = _stable_seed(equipment_id, cur)
            out.append(
                {
                    "observed_at": cur.isoformat(),
                    "params": _generate_params(eq_type, seed),
                }
            )
            cur += step
        return out

    @staticmethod
    def _resolve_type(equipment_id: UUID) -> EquipmentType:
        # В прототипе берём из хеша id, чтобы разные id давали разные типы.
        # В реальной интеграции тип придёт из БД.
        types = list(EquipmentType)
        idx = sum(int(x, 16) for x in equipment_id.hex[:8]) % len(types)
        return types[idx]


# Singleton
mock_adapter = MockAsutpAdapter()
