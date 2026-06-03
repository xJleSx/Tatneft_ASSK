"""Тесты /telemetry/.../history: ограничение окна и happy path."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.models.equipment import Equipment, EquipmentType
from app.models.object import Object, ObjectKind
from app.models.telemetry import TelemetryKind, TelemetryReading


@pytest.mark.asyncio
async def test_history_default_24h_works(
    client: AsyncClient, db_session, manager_user, manager_token
):
    obj = Object(id=uuid4(), name="Куст 200", code="OBJ-200", kind=ObjectKind.CLUSTER)
    db_session.add(obj)
    await db_session.flush()
    eq = Equipment(
        id=uuid4(),
        object_id=obj.id,
        serial_number="EQ-200-1",
        type=EquipmentType.USHGN,
    )
    db_session.add(eq)
    await db_session.flush()
    db_session.add(
        TelemetryReading(
            id=uuid4(),
            equipment_id=eq.id,
            observed_at=datetime.now(UTC) - timedelta(hours=1),
            kind=TelemetryKind.SCRAPE,
            params={"P_buf": 10.0},
            source="mock",
        )
    )
    await db_session.commit()

    r = await client.get(
        f"/api/v1/telemetry/equipment/{eq.id}/history",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_history_rejects_hours_above_max(
    client: AsyncClient, db_session, manager_user, manager_token
):
    """Больше 168 часов — 422 от FastAPI Query-валидатора."""
    r = await client.get(
        "/api/v1/telemetry/equipment/00000000-0000-0000-0000-000000000000/history?hours=200",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert r.status_code == 422
    body = r.json()
    assert any(
        "hours" in (err.get("loc") or []) for err in body.get("detail", [])
    )


@pytest.mark.asyncio
async def test_history_rejects_hours_zero(
    client: AsyncClient, manager_user, manager_token
):
    """hours=0 — тоже 422."""
    r = await client.get(
        "/api/v1/telemetry/equipment/00000000-0000-0000-0000-000000000000/history?hours=0",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_history_accepts_168(
    client: AsyncClient, db_session, manager_user, manager_token
):
    """Граничное значение 168 проходит (ровно неделя)."""
    r = await client.get(
        "/api/v1/telemetry/equipment/00000000-0000-0000-0000-000000000000/history?hours=168",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    # 200, даже если данных нет
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_history_excludes_readings_outside_window(
    client: AsyncClient, db_session, manager_user, manager_token
):
    """Чтение старше окна в hours=1 не попадает в выборку."""
    obj = Object(id=uuid4(), name="Куст 300", code="OBJ-300", kind=ObjectKind.CLUSTER)
    db_session.add(obj)
    await db_session.flush()
    eq = Equipment(
        id=uuid4(),
        object_id=obj.id,
        serial_number="EQ-300-1",
        type=EquipmentType.UECN,
    )
    db_session.add(eq)
    await db_session.flush()
    db_session.add(
        TelemetryReading(
            id=uuid4(),
            equipment_id=eq.id,
            observed_at=datetime.now(UTC) - timedelta(hours=10),
            kind=TelemetryKind.SCRAPE,
            params={"old": True},
            source="mock",
        )
    )
    await db_session.commit()

    r = await client.get(
        f"/api/v1/telemetry/equipment/{eq.id}/history?hours=1",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert r.status_code == 200
    assert r.json() == []
