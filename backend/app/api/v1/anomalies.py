"""Anomalies: детектор аномалий телеметрии (compute-on-the-fly, без отдельной таблицы)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.object import Object
from app.models.user import User
from app.services.anomaly_detector import detect_anomalies

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("/")
async def list_anomalies(
    object_id: UUID | None = Query(None, description="Фильтр по объекту (куст/скважина)"),
    min_severity: str | None = Query(None, description="warning | critical"),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    """Список аномалий по всем установкам.

    Лёгкий, без агрегатов — на MVP хватает; при больших объёмах
    стоит кэшировать в Redis или делать scheduled job.
    """
    anomalies = await detect_anomalies(session)

    # Подтягиваем имена объектов одним запросом
    object_ids = {a.object_id for a in anomalies if a.object_id}
    name_by_id: dict[UUID, str] = {}
    if object_ids:
        rows = (await session.scalars(select(Object).where(Object.id.in_(object_ids)))).all()
        name_by_id = {o.id: o.name for o in rows}

    items: list[dict] = []
    for a in anomalies:
        if object_id and a.object_id != object_id:
            continue
        if min_severity == "critical" and a.severity != "critical":
            continue
        a.object_name = name_by_id.get(a.object_id) if a.object_id else None
        items.append(a.to_dict())

    return {
        "items": items,
        "total": len(items),
        "critical": sum(1 for x in items if x["severity"] == "critical"),
        "warning": sum(1 for x in items if x["severity"] == "warning"),
    }
