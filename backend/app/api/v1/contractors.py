"""Contractors: подрядчики."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.contractor import Contractor
from app.models.user import User

router = APIRouter(prefix="/contractors", tags=["contractors"])


@router.get("/")
async def list_contractors(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[dict]:
    rows = (await session.scalars(select(Contractor).order_by(Contractor.name))).all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "inn": c.inn,
            "is_active": c.is_active,
            "rating_score": float(c.rating_score),
            "specializations": c.specializations,
        }
        for c in rows
    ]


@router.get("/{contractor_id}")
async def get_contractor(
    contractor_id: str,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    from uuid import UUID

    c = await session.get(Contractor, UUID(contractor_id))
    if not c:
        from fastapi import HTTPException

        raise HTTPException(404, "Не найден")
    return {
        "id": str(c.id),
        "name": c.name,
        "inn": c.inn,
        "is_active": c.is_active,
        "rating_score": float(c.rating_score),
        "specializations": c.specializations,
        "contact_email": c.contact_email,
        "contact_phone": c.contact_phone,
    }
