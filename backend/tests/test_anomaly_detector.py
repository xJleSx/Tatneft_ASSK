"""Тесты app/services/anomaly_detector.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.anomaly_detector import (
    _ANOMALY_TO_WT,
    SEVERITY_RANK,
    Anomaly,
    _avg,
    _detect_for_equipment,
    _extract_param_series,
    _split_current_vs_baseline,
    detect_anomalies,
)

# ---------- helpers ----------


def make_eq(eq_type: str = "uecn", serial: str = "EQ-1", obj_id=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        serial_number=serial,
        type=SimpleNamespace(value=eq_type),
        object_id=obj_id or uuid4(),
    )


def make_reading(eq_id, params: dict, hours_ago: float) -> SimpleNamespace:
    return SimpleNamespace(
        equipment_id=eq_id,
        observed_at=datetime.now(UTC) - timedelta(hours=hours_ago),
        params=params,
    )


# ---------- _avg ----------


def test_avg_empty():
    assert _avg([]) is None


def test_avg_filters_none():
    assert _avg([1, None, 2, None, 3]) == pytest.approx(2.0)


def test_avg_all_none():
    assert _avg([None, None]) is None


def test_avg_normal():
    assert _avg([10, 20]) == pytest.approx(15.0)


# ---------- _extract_param_series ----------


def test_extract_param_series_sorts_by_time():
    eq_id = uuid4()
    readings = [
        make_reading(eq_id, {"Q_liq": 5}, hours_ago=2),
        make_reading(eq_id, {"Q_liq": 10}, hours_ago=10),
        make_reading(eq_id, {"Q_liq": 7}, hours_ago=5),
    ]
    series = _extract_param_series(readings, "Q_liq")
    assert [v for _, v in series] == [10, 7, 5]  # sorted ascending


def test_extract_param_series_skips_non_numeric():
    eq_id = uuid4()
    readings = [
        make_reading(eq_id, {"Q_liq": "bad"}, hours_ago=1),
        make_reading(eq_id, {"Q_liq": 5}, hours_ago=1),
    ]
    series = _extract_param_series(readings, "Q_liq")
    assert len(series) == 1
    assert series[0][1] == 5.0


def test_extract_param_series_missing_key():
    eq_id = uuid4()
    readings = [make_reading(eq_id, {"I": 50}, hours_ago=1)]
    assert _extract_param_series(readings, "Q_liq") == []


# ---------- _split_current_vs_baseline ----------


def test_split_current_vs_baseline_partitions():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    series = [
        (now - timedelta(hours=1), 100),  # current (within 6h)
        (now - timedelta(hours=5), 200),  # current
        (now - timedelta(hours=7), 300),  # baseline (6-30h)
        (now - timedelta(hours=20), 400),  # baseline
        (now - timedelta(hours=40), 500),  # dropped
    ]
    current, baseline = _split_current_vs_baseline(series, now)
    assert current == [100, 200]
    assert baseline == [300, 400]


# ---------- _detect_for_equipment: data_gap ----------


def test_detect_for_equipment_no_readings():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    out = _detect_for_equipment(eq, [], now)
    assert len(out) == 1
    assert out[0].code == "data_gap"
    assert out[0].severity == "critical"
    assert out[0].suggested_work_type_code == "DIAGNOSTIC"


def test_detect_for_equipment_old_data():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    readings = [make_reading(eq.id, {"Q_liq": 50}, hours_ago=10)]
    out = _detect_for_equipment(eq, readings, now)
    # Должна быть data_gap аномалия
    assert any(a.code == "data_gap" for a in out)


def test_detect_for_equipment_fresh_data_no_anomaly():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    # 8 baseline + 2 current с одинаковым Q_liq
    readings = []
    for i in range(15):
        readings.append(make_reading(eq.id, {"Q_liq": 50.0}, hours_ago=i))
    out = _detect_for_equipment(eq, readings, now)
    # Нет аномалий (Q_liq = 50/50 = 1.0, в пределах нормы)
    assert all(a.code != "debit_drop" for a in out)


# ---------- _detect_for_equipment: debit_drop ----------


def test_detect_debit_drop_warning():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    readings = []
    # 4 точки в текущем окне (0-3ч назад): Q=70
    for h in (0, 1, 2, 3):
        readings.append(make_reading(eq.id, {"Q_liq": 70.0}, hours_ago=h))
    # 10 точек в baseline (7-16ч назад): Q=100
    for h in range(7, 17):
        readings.append(make_reading(eq.id, {"Q_liq": 100.0}, hours_ago=h))
    out = _detect_for_equipment(eq, readings, now)
    deb = [a for a in out if a.code == "debit_drop"]
    assert len(deb) == 1
    assert deb[0].severity == "warning"
    assert deb[0].parameter == "Q_liq"
    assert deb[0].ratio == pytest.approx(0.7, abs=0.01)


def test_detect_debit_drop_critical():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    readings = []
    for h in (0, 1, 2, 3):
        readings.append(make_reading(eq.id, {"Q_liq": 50.0}, hours_ago=h))
    for h in range(7, 17):
        readings.append(make_reading(eq.id, {"Q_liq": 100.0}, hours_ago=h))
    out = _detect_for_equipment(eq, readings, now)
    deb = [a for a in out if a.code == "debit_drop_critical"]
    assert len(deb) == 1
    assert deb[0].severity == "critical"
    assert deb[0].suggested_work_type_code == "TR-1"


# ---------- _detect_for_equipment: motor_overload ----------


def test_detect_motor_overload_warning():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    readings = []
    for h in (0, 1, 2, 3):
        readings.append(make_reading(eq.id, {"I": 120.0}, hours_ago=h))
    for h in range(7, 17):
        readings.append(make_reading(eq.id, {"I": 100.0}, hours_ago=h))
    out = _detect_for_equipment(eq, readings, now)
    mo = [a for a in out if a.code == "motor_overload"]
    assert len(mo) == 1
    assert mo[0].severity == "warning"
    assert mo[0].suggested_work_type_code == "REPLACE-UECN"


def test_detect_motor_overload_critical():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    readings = []
    for h in (0, 1, 2, 3):
        readings.append(make_reading(eq.id, {"I": 140.0}, hours_ago=h))
    for h in range(7, 17):
        readings.append(make_reading(eq.id, {"I": 100.0}, hours_ago=h))
    out = _detect_for_equipment(eq, readings, now)
    mo = [a for a in out if a.code == "motor_overload"]
    assert len(mo) == 1
    assert mo[0].severity == "critical"


# ---------- _detect_for_equipment: motor_overheat ----------


def test_detect_motor_overheat_warning():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    readings = []
    for h in (0, 1, 2, 3):
        readings.append(make_reading(eq.id, {"T_motor": 115.0}, hours_ago=h))
    for h in range(7, 17):
        readings.append(make_reading(eq.id, {"T_motor": 80.0}, hours_ago=h))
    out = _detect_for_equipment(eq, readings, now)
    mo = [a for a in out if a.code == "motor_overheat"]
    assert len(mo) == 1
    assert mo[0].severity == "warning"


def test_detect_motor_overheat_critical():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    readings = []
    for h in (0, 1, 2, 3):
        readings.append(make_reading(eq.id, {"T_motor": 130.0}, hours_ago=h))
    for h in range(7, 17):
        readings.append(make_reading(eq.id, {"T_motor": 80.0}, hours_ago=h))
    out = _detect_for_equipment(eq, readings, now)
    mo = [a for a in out if a.code == "motor_overheat"]
    assert len(mo) == 1
    assert mo[0].severity == "critical"


# ---------- _detect_for_equipment: pressure_high (wellhead) ----------


def test_detect_pressure_high_wellhead():
    eq = make_eq("wellhead")
    now = datetime.now(UTC)
    readings = []
    for h in (0, 1, 2, 3):
        readings.append(make_reading(eq.id, {"P_buf": 15.0}, hours_ago=h))
    for h in range(7, 17):
        readings.append(make_reading(eq.id, {"P_buf": 10.0}, hours_ago=h))
    out = _detect_for_equipment(eq, readings, now)
    ph = [a for a in out if a.code == "pressure_high"]
    assert len(ph) == 1
    assert ph[0].severity == "warning"
    assert ph[0].suggested_work_type_code == "TO-WELLHEAD"


# ---------- _detect_for_equipment: pressure_low (ushgn) ----------


def test_detect_pressure_low_ushgn():
    eq = make_eq("ushgn")
    now = datetime.now(UTC)
    readings = []
    for h in (0, 1, 2, 3):
        readings.append(make_reading(eq.id, {"P_buf": 5.0}, hours_ago=h))  # 50%
    for h in range(7, 17):
        readings.append(make_reading(eq.id, {"P_buf": 10.0}, hours_ago=h))
    out = _detect_for_equipment(eq, readings, now)
    pl = [a for a in out if a.code == "pressure_low"]
    assert len(pl) == 1
    assert pl[0].severity == "warning"


# ---------- _detect_for_equipment: edge cases ----------


def test_detect_unknown_equipment_type():
    eq = make_eq("unknown_type")
    now = datetime.now(UTC)
    readings = []
    for h in (0, 1, 2, 3):
        readings.append(make_reading(eq.id, {"Q_liq": 30.0}, hours_ago=h))
    for h in range(7, 17):
        readings.append(make_reading(eq.id, {"Q_liq": 100.0}, hours_ago=h))
    out = _detect_for_equipment(eq, readings, now)
    # Универсально проверяется Q_liq → debit_drop
    assert any(a.code == "debit_drop_critical" for a in out)


def test_detect_too_few_baseline_points():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    # Только 2 точки (меньше MIN_BASELINE_POINTS=8)
    readings = [
        make_reading(eq.id, {"Q_liq": 10}, hours_ago=1),
        make_reading(eq.id, {"Q_liq": 100}, hours_ago=10),
    ]
    out = _detect_for_equipment(eq, readings, now)
    # baseline < MIN_BASELINE_POINTS → пропуск
    assert all(a.code != "debit_drop" for a in out)


def test_detect_param_missing_in_baseline_but_in_current():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    readings = []
    for i in range(15):
        if i < 2:
            v = 30.0
        else:
            v = None
        readings.append(make_reading(eq.id, {"Q_liq": v}, hours_ago=i))
    out = _detect_for_equipment(eq, readings, now)
    # baseline пустой → пропуск
    assert all(a.code != "debit_drop" for a in out)


def test_detect_baseline_zero():
    eq = make_eq("uecn")
    now = datetime.now(UTC)
    readings = []
    for i in range(15):
        readings.append(make_reading(eq.id, {"Q_liq": 0.0 if i >= 2 else 5.0}, hours_ago=i))
    out = _detect_for_equipment(eq, readings, now)
    # base <= 0 → пропуск
    assert all(a.code != "debit_drop" for a in out)


# ---------- Anomaly dataclass ----------


def test_anomaly_to_dict():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    obj_id = uuid4()
    a = Anomaly(
        equipment_id=uuid4(),
        equipment_serial="EQ-1",
        equipment_type="uecn",
        object_id=obj_id,
        object_name=None,
        code="debit_drop",
        severity="warning",
        parameter="Q_liq",
        current_value=70.0,
        baseline_value=100.0,
        ratio=0.7,
        unit="м³/сут",
        detected_at=now,
        description="test",
        suggested_work_type_code="TR-1",
    )
    d = a.to_dict()
    assert d["code"] == "debit_drop"
    assert d["object_id"] == str(obj_id)
    assert d["detected_at"] == "2026-01-01T00:00:00+00:00"


def test_anomaly_to_dict_no_object():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    a = Anomaly(
        equipment_id=uuid4(),
        equipment_serial="EQ-1",
        equipment_type="uecn",
        object_id=None,
        object_name=None,
        code="data_gap",
        severity="critical",
        parameter="any",
        current_value=None,
        baseline_value=None,
        ratio=None,
        unit=None,
        detected_at=now,
        description="test",
    )
    d = a.to_dict()
    assert d["object_id"] is None


# ---------- detect_anomalies (DB-level) ----------


@pytest.mark.asyncio
async def test_detect_anomalies_empty_equipment_list():
    """Нет оборудования → пустой список."""
    session = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    scalars.first.return_value = None
    scalars.scalar.return_value = None
    session.scalars = AsyncMock(return_value=scalars)
    result = await detect_anomalies(session)
    assert result == []


@pytest.mark.asyncio
async def test_detect_anomalies_with_data():
    """Один UECN с аномалией debit_drop_critical."""
    session = AsyncMock()
    eq = make_eq("uecn")
    eq_list = [eq]
    readings = []
    for h in (0, 1, 2, 3):
        readings.append(make_reading(eq.id, {"Q_liq": 50.0}, hours_ago=h))
    for h in range(7, 17):
        readings.append(make_reading(eq.id, {"Q_liq": 100.0}, hours_ago=h))

    call_count = {"n": 0}

    async def scalars_side_effect(*args, **kwargs):
        mock = MagicMock()
        if call_count["n"] == 0:
            mock.all.return_value = eq_list
        else:
            mock.all.return_value = readings
        call_count["n"] += 1
        return mock

    session.scalars = AsyncMock(side_effect=scalars_side_effect)
    result = await detect_anomalies(session)
    assert any(a.code == "debit_drop_critical" for a in result)


# ---------- SEVERITY_RANK ----------


def test_severity_rank_ordering():
    assert SEVERITY_RANK["warning"] < SEVERITY_RANK["critical"]


# ---------- _ANOMALY_TO_WT mapping ----------


def test_anomaly_to_wt_mapping_complete():
    """Все коды аномалий имеют рекомендацию."""
    expected = {
        "debit_drop",
        "debit_drop_critical",
        "pressure_high",
        "pressure_low",
        "motor_overload",
        "motor_overheat",
        "data_gap",
    }
    assert set(_ANOMALY_TO_WT.keys()) == expected
