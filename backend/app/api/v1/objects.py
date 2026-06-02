"""Objects: производственные объекты и оборудование."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.equipment import Equipment
from app.models.object import Object, ObjectKind
from app.models.user import User

router = APIRouter(prefix="/objects", tags=["objects"])


@router.get("/")
async def list_objects(
    kind: ObjectKind | None = None,
    parent_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[dict]:
    q = select(Object).order_by(Object.name)
    if kind:
        q = q.where(Object.kind == kind)
    if parent_id:
        q = q.where(Object.parent_id == parent_id)
    rows = (await session.scalars(q)).all()
    return [
        {
            "id": str(o.id),
            "name": o.name,
            "code": o.code,
            "kind": o.kind.value,
            "parent_id": str(o.parent_id) if o.parent_id else None,
            "latitude": float(o.latitude) if o.latitude else None,
            "longitude": float(o.longitude) if o.longitude else None,
        }
        for o in rows
    ]


@router.get("/{object_id}/equipment")
async def list_equipment(
    object_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[dict]:
    rows = (
        await session.scalars(
            select(Equipment).where(Equipment.object_id == object_id)
        )
    ).all()
    return [
        {
            "id": str(e.id),
            "type": e.type.value,
            "serial_number": e.serial_number,
            "manufacturer": e.manufacturer,
            "model": e.model,
            "commissioned_at": e.commissioned_at.isoformat() if e.commissioned_at else None,
        }
        for e in rows
    ]
