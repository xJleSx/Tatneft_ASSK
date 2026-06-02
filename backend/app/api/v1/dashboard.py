"""Dashboard: агрегаты для UI."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.act import Act, ActStatus
from app.models.contractor import Contractor
from app.models.order import WorkOrder, WorkOrderStatus
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    """Верхнеуровневая сводка для главной страницы."""
    total_orders = await session.scalar(select(func.count(WorkOrder.id))) or 0
    total_acts = await session.scalar(select(func.count(Act.id))) or 0
    auto_confirmed = (
        await session.scalar(
            select(func.count(Act.id)).where(Act.status == ActStatus.AUTO_CONFIRMED)
        )
        or 0
    )
    pending_review = (
        await session.scalar(
            select(func.count(Act.id)).where(
                Act.status.in_([ActStatus.SUBMITTED, ActStatus.DELAYED_VERIFICATION])
            )
        )
        or 0
    )
    rejected = (
        await session.scalar(
            select(func.count(Act.id)).where(Act.status == ActStatus.REJECTED)
        )
        or 0
    )

    last_30d = datetime.now(timezone.utc) - timedelta(days=30)
    recent_acts = await session.scalar(
        select(func.count(Act.id)).where(Act.created_at >= last_30d)
    ) or 0

    return {
        "total_work_orders": total_orders,
        "total_acts": total_acts,
        "auto_confirmed": auto_confirmed,
        "pending_review": pending_review,
        "rejected": rejected,
        "auto_confirmation_rate": (
            round(auto_confirmed / total_acts, 3) if total_acts else 0.0
        ),
        "acts_last_30d": recent_acts,
    }


@router.get("/contractors/ranking")
async def contractor_ranking(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[dict]:
    rows = (
        await session.scalars(
            select(Contractor).order_by(Contractor.rating_score.desc())
        )
    ).all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "rating_score": float(c.rating_score),
        }
        for c in rows
    ]


@router.get("/orders/recent")
async def recent_orders(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[dict]:
    rows = (
        await session.scalars(
            select(WorkOrder).order_by(WorkOrder.created_at.desc()).limit(limit)
        )
    ).all()
    return [
        {
            "id": str(o.id),
            "number": o.number,
            "status": o.status.value,
            "object_id": str(o.object_id),
            "contractor_id": str(o.contractor_id) if o.contractor_id else None,
            "created_at": o.created_at.isoformat(),
        }
        for o in rows
    ]
