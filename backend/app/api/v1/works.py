"""Work types & checklist templates."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.models.work import ChecklistTemplate, WorkType

router = APIRouter(prefix="/works", tags=["works"])


@router.get("/types")
async def list_work_types(
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[dict]:
    rows = (await session.scalars(select(WorkType).order_by(WorkType.code))).all()
    return [
        {
            "id": str(w.id),
            "code": w.code,
            "name": w.name,
            "category": w.category.value,
            "planned_duration_hours": (
                float(w.planned_duration_hours) if w.planned_duration_hours else None
            ),
            "applies_to_equipment_type": w.applies_to_equipment_type,
        }
        for w in rows
    ]


@router.get("/types/{work_type_id}/template")
async def get_template(
    work_type_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    tpl = await session.scalar(
        select(ChecklistTemplate).where(
            ChecklistTemplate.work_type_id == work_type_id,
            ChecklistTemplate.is_active.is_(True),
        )
    )
    if not tpl:
        return {"steps": []}
    # Явная загрузка шагов (lazy="noload" на relationship)
    from app.models.work import ChecklistStep

    steps_rows = (
        await session.scalars(
            select(ChecklistStep)
            .where(ChecklistStep.template_id == tpl.id)
            .order_by(ChecklistStep.order_index)
        )
    ).all()
    steps = [
        {
            "id": str(s.id),
            "order_index": s.order_index,
            "title": s.title,
            "description": s.description,
            "data_type": s.data_type.value,
            "is_required": s.is_required,
            "norm_json": s.norm_json,
            "telemetry_param": s.telemetry_param,
        }
        for s in steps_rows
    ]
    return {"template_id": str(tpl.id), "version": tpl.version, "steps": steps}
