"""Базовый интерфейс адаптера АСУ ТП.

Контракт (определён на основе аналогов):
- УЭЦН: P_buf, P_lin, P_intake, T_motor, I, V_freq, Q_liq
- УШГН: P_buf, P_lin, Q_liq, level_dynamic, strokes_per_min
- Устьевая арматура: P_buf, T_buf, P_obv

Подробное обоснование см. docs/analogs.md.
"""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Any
from uuid import UUID


class AsutpAdapter(abc.ABC):
    """Получить текущие и исторические параметры оборудования."""

    @abc.abstractmethod
    async def get_snapshot(self, equipment_id: UUID, at: datetime | None = None) -> dict[str, Any]:
        """Снимок параметров equipment на момент времени (или сейчас)."""

    @abc.abstractmethod
    async def get_history(
        self,
        equipment_id: UUID,
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        """Исторический ряд точек: [{observed_at, params}, ...]"""
