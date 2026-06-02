"""Детектор аномалий телеметрии.

Для MVP — простые статистические правила по каждой единице оборудования:
  - сравниваем «свежее» окно (CURRENT_WINDOW_HOURS) с «базовым» окном
    (BASELINE_WINDOW_HOURS, идёт сразу перед свежим);
  - помечаем отклонения по порогам DEBIT_DROP / PRESSURE_HIGH / MOTOR_OVERLOAD;
  - отдельно ловим «пропуски» данных (gap > DATA_GAP_HOURS).

Тяжёлой аналитики нет — это намеренно: прототип должен объясняться
«на пальцах» в презентации.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.equipment import Equipment
from app.models.telemetry import TelemetryReading

log = get_logger(__name__)

CURRENT_WINDOW_HOURS = 6
BASELINE_WINDOW_HOURS = 24  # baseline = 24-30ч назад
MIN_BASELINE_POINTS = 8  # минимум точек, чтобы не флапать на пустоте
DATA_GAP_HOURS = 4  # «нет данных» — последняя точка старше

# Пороги — консервативные, чтобы не плодить ложные
DEBIT_DROP_RATIO = 0.80  # current < 80% baseline → warning
DEBIT_DROP_RATIO_CRITICAL = 0.60  # < 60% — critical

PRESSURE_HIGH_RATIO = 1.30
PRESSURE_LOW_RATIO = 0.70

MOTOR_CURRENT_HIGH_RATIO = 1.15
MOTOR_TEMP_HIGH_C = 110.0
MOTOR_TEMP_CRITICAL_C = 125.0


SEVERITY_RANK = {"warning": 1, "critical": 2}


@dataclass
class Anomaly:
    equipment_id: UUID
    equipment_serial: str | None
    equipment_type: str | None
    object_id: UUID | None
    object_name: str | None
    code: str
    severity: str  # "warning" | "critical"
    parameter: str
    current_value: float | None
    baseline_value: float | None
    ratio: float | None
    unit: str | None
    detected_at: datetime
    description: str
    suggested_work_type_code: str | None = None

    def to_dict(self) -> dict:
        return {
            "equipment_id": str(self.equipment_id),
            "equipment_serial": self.equipment_serial,
            "equipment_type": self.equipment_type,
            "object_id": str(self.object_id) if self.object_id else None,
            "object_name": self.object_name,
            "code": self.code,
            "severity": self.severity,
            "parameter": self.parameter,
            "current_value": self.current_value,
            "baseline_value": self.baseline_value,
            "ratio": self.ratio,
            "unit": self.unit,
            "detected_at": self.detected_at.isoformat(),
            "description": self.description,
            "suggested_work_type_code": self.suggested_work_type_code,
        }


# Маппинг аномалии → рекомендуемый тип работ.
# Завязан на коды видов работ, засеянных в seed (см. WORK_TYPES в seed.py).
_ANOMALY_TO_WT: dict[str, str] = {
    "debit_drop": "TR-1",
    "debit_drop_critical": "TR-1",
    "pressure_high": "TO-WELLHEAD",
    "pressure_low": "TR-1",
    "motor_overload": "REPLACE-UECN",
    "motor_overheat": "REPLACE-UECN",
    "data_gap": "DIAGNOSTIC",
}


def _avg(vals: Iterable[float]) -> float | None:
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return statistics.fmean(vals)


def _extract_param_series(
    readings: list[TelemetryReading], param: str
) -> list[tuple[datetime, float]]:
    out: list[tuple[datetime, float]] = []
    for r in readings:
        v = r.params.get(param)
        if isinstance(v, (int, float)):
            out.append((r.observed_at, float(v)))
    out.sort(key=lambda t: t[0])
    return out


def _split_current_vs_baseline(
    series: list[tuple[datetime, float]], now: datetime
) -> tuple[list[float], list[float]]:
    cur_from = now - timedelta(hours=CURRENT_WINDOW_HOURS)
    base_from = cur_from - timedelta(hours=BASELINE_WINDOW_HOURS)
    current: list[float] = []
    baseline: list[float] = []
    for ts, v in series:
        if ts >= cur_from:
            current.append(v)
        elif ts >= base_from:
            baseline.append(v)
    return current, baseline


def _detect_for_equipment(
    equipment: Equipment, readings: list[TelemetryReading], now: datetime
) -> list[Anomaly]:
    out: list[Anomaly] = []
    eq = equipment
    # Получаем последний observed_at (для gap)
    if not readings:
        out.append(
            Anomaly(
                equipment_id=eq.id,
                equipment_serial=eq.serial_number,
                equipment_type=eq.type.value if eq.type else None,
                object_id=eq.object_id,
                object_name=None,
                code="data_gap",
                severity="critical",
                parameter="any",
                current_value=None,
                baseline_value=None,
                ratio=None,
                unit=None,
                detected_at=now,
                description="Нет данных телеметрии",
                suggested_work_type_code=_ANOMALY_TO_WT["data_gap"],
            )
        )
        return out

    readings_sorted = sorted(readings, key=lambda r: r.observed_at)
    last_seen = readings_sorted[-1].observed_at
    gap_hours = (now - last_seen).total_seconds() / 3600.0
    if gap_hours > DATA_GAP_HOURS:
        out.append(
            Anomaly(
                equipment_id=eq.id,
                equipment_serial=eq.serial_number,
                equipment_type=eq.type.value if eq.type else None,
                object_id=eq.object_id,
                object_name=None,
                code="data_gap",
                severity="critical",
                parameter="any",
                current_value=None,
                baseline_value=None,
                ratio=None,
                unit=None,
                detected_at=now,
                description=f"Нет данных {gap_hours:.1f} ч (с {last_seen:%Y-%m-%d %H:%M} UTC)",
                suggested_work_type_code=_ANOMALY_TO_WT["data_gap"],
            )
        )

    # Анализируем по параметрам
    type_specific_params: list[tuple[str, str, str | None]] = []
    t = eq.type.value if eq.type else ""
    if t == "uecn":
        type_specific_params = [
            ("Q_liq", "debit_drop", "м³/сут"),
            ("I", "motor_overload", "А"),
            ("T_motor", "motor_overheat", "°C"),
        ]
    elif t == "ushgn":
        type_specific_params = [
            ("Q_liq", "debit_drop", "м³/сут"),
            ("P_buf", "pressure_low", "атм"),
        ]
    elif t == "wellhead":
        type_specific_params = [
            ("P_buf", "pressure_high", "атм"),
        ]
    else:
        # Универсально
        type_specific_params = [("Q_liq", "debit_drop", "м³/сут")]

    for param, code, unit in type_specific_params:
        series = _extract_param_series(readings_sorted, param)
        if not series:
            continue
        current_vals, baseline_vals = _split_current_vs_baseline(series, now)
        if len(baseline_vals) < MIN_BASELINE_POINTS:
            continue
        cur = _avg(current_vals)
        base = _avg(baseline_vals)
        if cur is None or base is None or base <= 0:
            continue
        ratio = cur / base

        # Решающие правила
        if code == "debit_drop":
            if ratio < DEBIT_DROP_RATIO_CRITICAL:
                sev = "critical"
                actual_code = "debit_drop_critical"
            elif ratio < DEBIT_DROP_RATIO:
                sev = "warning"
                actual_code = "debit_drop"
            else:
                continue
            desc = f"Дебит {param} = {cur:.1f} {unit} " f"({ratio*100:.0f}% от базовых {base:.1f})"
        elif code == "motor_overload":
            if ratio < MOTOR_CURRENT_HIGH_RATIO:
                continue
            sev = "critical" if ratio > 1.30 else "warning"
            actual_code = "motor_overload"
            desc = f"Ток двигателя {cur:.1f} {unit} ({ratio*100:.0f}% от базовых {base:.1f})"
        elif code == "motor_overheat":
            if cur < MOTOR_TEMP_HIGH_C:
                continue
            sev = "critical" if cur > MOTOR_TEMP_CRITICAL_C else "warning"
            actual_code = "motor_overheat"
            desc = f"Температура двигателя {cur:.0f} {unit}"
        elif code == "pressure_high":
            if ratio < PRESSURE_HIGH_RATIO:
                continue
            sev = "warning"
            actual_code = "pressure_high"
            desc = f"Давление {cur:.2f} {unit} ({ratio*100:.0f}% от базовых {base:.2f})"
        elif code == "pressure_low":
            if ratio > PRESSURE_LOW_RATIO:
                continue
            sev = "warning"
            actual_code = "pressure_low"
            desc = f"Давление {cur:.2f} {unit} ({ratio*100:.0f}% от базовых {base:.2f})"
        else:
            continue

        out.append(
            Anomaly(
                equipment_id=eq.id,
                equipment_serial=eq.serial_number,
                equipment_type=t or None,
                object_id=eq.object_id,
                object_name=None,
                code=actual_code,
                severity=sev,
                parameter=param,
                current_value=round(cur, 3),
                baseline_value=round(base, 3),
                ratio=round(ratio, 3),
                unit=unit,
                detected_at=now,
                description=desc,
                suggested_work_type_code=_ANOMALY_TO_WT.get(actual_code),
            )
        )
    return out


async def detect_anomalies(session: AsyncSession) -> list[Anomaly]:
    """Compute-on-the-fly: за последние (CURRENT+BASELINE) часов на каждую установку."""
    now = datetime.now(UTC)
    horizon_from = now - timedelta(hours=CURRENT_WINDOW_HOURS + BASELINE_WINDOW_HOURS)

    equipment_list = (await session.scalars(select(Equipment))).all()
    if not equipment_list:
        return []

    eq_ids = [e.id for e in equipment_list]
    readings = (
        await session.scalars(
            select(TelemetryReading)
            .where(
                TelemetryReading.equipment_id.in_(eq_ids),
                TelemetryReading.observed_at >= horizon_from,
            )
            .order_by(TelemetryReading.observed_at)
        )
    ).all()

    by_eq: dict[UUID, list[TelemetryReading]] = {eid: [] for eid in eq_ids}
    for r in readings:
        by_eq[r.equipment_id].append(r)

    anomalies: list[Anomaly] = []
    for eq in equipment_list:
        anomalies.extend(_detect_for_equipment(eq, by_eq.get(eq.id, []), now))

    # Сортируем по severity (critical first) и времени
    anomalies.sort(key=lambda a: (-SEVERITY_RANK.get(a.severity, 0), a.detected_at, a.equipment_id))
    return anomalies
