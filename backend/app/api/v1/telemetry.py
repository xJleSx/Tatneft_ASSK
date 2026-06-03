"""Telemetry: снимки и история параметров equipment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.integrations.asutp.factory import get_asutp_adapter
from app.models.telemetry import TelemetryReading
from app.models.user import User

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Чтобы клиент не мог забрать всю БД за год одной выборкой.
MAX_HISTORY_HOURS = 168  # неделя


@router.get("/equipment/{equipment_id}/snapshot")
async def snapshot(
    equipment_id: UUID,
    _: User = Depends(get_current_user),
) -> dict:
    """Снимок параметров сейчас (мок)."""
    return await get_asutp_adapter().get_snapshot(equipment_id)


@router.get("/equipment/{equipment_id}/history")
async def history(
    equipment_id: UUID,
    hours: int = Query(
        24,
        ge=1,
        le=MAX_HISTORY_HOURS,
        description=f"Окно истории в часах, максимум {MAX_HISTORY_HOURS} (неделя).",
    ),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[dict]:
    """История из БД (накопленная при опросе)."""
    if hours < 1 or hours > MAX_HISTORY_HOURS:
        raise HTTPException(
            400,
            f"hours должно быть в [1, {MAX_HISTORY_HOURS}]",
        )
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = (
        await session.scalars(
            select(TelemetryReading)
            .where(
                TelemetryReading.equipment_id == equipment_id,
                TelemetryReading.observed_at >= since,
            )
            .order_by(TelemetryReading.observed_at)
        )
    ).all()
    return [
        {
            "observed_at": r.observed_at.isoformat(),
            "params": r.params,
            "source": r.source,
        }
        for r in rows
    ]
