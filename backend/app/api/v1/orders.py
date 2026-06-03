"""Work orders (наряды-заказы)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models.order import WorkOrder, WorkOrderStatus, assert_transition
from app.models.user import User, UserRole
from app.schemas.order import WorkOrderCreate, WorkOrderOut, WorkOrderUpdate

router = APIRouter(prefix="/orders", tags=["orders"])


def _gen_number() -> str:
    # 6 hex символов из secrets — гарантированно уникально в пределах дня
    suffix = secrets.token_hex(3).upper()
    return f"WO-{datetime.utcnow().strftime('%Y%m%d')}-{suffix}"


@router.get("/", response_model=list[WorkOrderOut])
async def list_orders(
    status: WorkOrderStatus | None = None,
    contractor_id: UUID | None = None,
    object_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[WorkOrder]:
    q = select(WorkOrder).order_by(WorkOrder.created_at.desc()).limit(limit).offset(offset)
    if status:
        q = q.where(WorkOrder.status == status)
    if contractor_id:
        q = q.where(WorkOrder.contractor_id == contractor_id)
    if object_id:
        q = q.where(WorkOrder.object_id == object_id)
    if user.role == UserRole.CONTRACTOR and user.contractor_id:
        q = q.where(WorkOrder.contractor_id == user.contractor_id)
    rows = (await session.scalars(q)).all()
    return list(rows)


@router.get("/{order_id}", response_model=WorkOrderOut)
async def get_order(
    order_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> WorkOrder:
    wo = await session.get(WorkOrder, order_id)
    if not wo:
        raise HTTPException(404, "Наряд не найден")
    if (
        user.role == UserRole.CONTRACTOR
        and user.contractor_id
        and wo.contractor_id != user.contractor_id
    ):
        raise HTTPException(403, "Чужой наряд")
    return wo


@router.post("/", response_model=WorkOrderOut, status_code=201)
async def create_order(
    body: WorkOrderCreate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles(UserRole.MANAGER, UserRole.ADMIN)),
) -> WorkOrder:
    wo = WorkOrder(
        number=_gen_number(),
        object_id=body.object_id,
        work_type_id=body.work_type_id,
        contractor_id=body.contractor_id,
        priority=body.priority,
        planned_start_at=body.planned_start_at,
        planned_end_at=body.planned_end_at,
        planned_cost=body.planned_cost,
        description=body.description,
        defect_ref=body.defect_ref,
        is_diagnostic=body.is_diagnostic,
        status=WorkOrderStatus.ASSIGNED if body.contractor_id else WorkOrderStatus.DRAFT,
    )
    session.add(wo)
    await session.commit()
    await session.refresh(wo)
    return wo


@router.patch("/{order_id}", response_model=WorkOrderOut)
async def update_order(
    order_id: UUID,
    body: WorkOrderUpdate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles(UserRole.MANAGER, UserRole.ADMIN)),
) -> WorkOrder:
    wo = await session.get(WorkOrder, order_id)
    if not wo:
        raise HTTPException(404, "Наряд не найден")
    data = body.model_dump(exclude_unset=True)
    new_status = data.get("status")
    if new_status is not None and new_status != wo.status:
        try:
            assert_transition(wo.status, new_status)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    for k, v in data.items():
        setattr(wo, k, v)
    await session.commit()
    await session.refresh(wo)
    return wo


@router.post("/{order_id}/start", response_model=WorkOrderOut)
async def start_order(
    order_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> WorkOrder:
    """Подрядчик берёт наряд в работу: assigned → in_progress."""
    wo = await session.get(WorkOrder, order_id)
    if not wo:
        raise HTTPException(404, "Наряд не найден")
    if (
        user.role == UserRole.CONTRACTOR
        and user.contractor_id
        and wo.contractor_id != user.contractor_id
    ):
        raise HTTPException(403, "Чужой наряд")
    try:
        assert_transition(wo.status, WorkOrderStatus.IN_PROGRESS)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    wo.status = WorkOrderStatus.IN_PROGRESS
    wo.actual_start_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(wo)
    return wo
