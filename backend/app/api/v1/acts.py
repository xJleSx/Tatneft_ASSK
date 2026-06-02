"""Acts: цифровые акты выполненных работ."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_session
from app.integrations.asutp.factory import get_asutp_adapter
from app.models.act import Act, ActStatus, ChecklistResponse
from app.models.equipment import Equipment
from app.models.object import Object
from app.models.order import WorkOrder, WorkOrderStatus
from app.models.photo import Photo, PhotoKind
from app.models.user import User, UserRole
from app.schemas.order import ActCreate, ActOut, ActReview, ActSubmit

router = APIRouter(prefix="/acts", tags=["acts"])


@router.get("/", response_model=list[ActOut])
async def list_acts(
    work_order_id: UUID | None = None,
    status: ActStatus | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    q = select(Act).order_by(Act.created_at.desc()).limit(limit)
    if work_order_id:
        q = q.where(Act.work_order_id == work_order_id)
    if status:
        q = q.where(Act.status == status)
    if user.role == UserRole.CONTRACTOR:
        q = q.where(Act.contractor_user_id == user.id)
    return (await session.scalars(q)).all()


@router.post("/", response_model=ActOut, status_code=201)
async def create_draft_act(
    body: ActCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_roles(UserRole.CONTRACTOR, UserRole.MASTER, UserRole.ADMIN)),
):
    wo = await session.get(WorkOrder, body.work_order_id)
    if not wo:
        raise HTTPException(404, "Наряд-заказ не найден")
    act = Act(
        work_order_id=body.work_order_id,
        contractor_user_id=user.id,
        status=ActStatus.DRAFT,
        actual_latitude=body.actual_latitude,
        actual_longitude=body.actual_longitude,
        actual_at=body.actual_at or datetime.now(timezone.utc),
    )
    session.add(act)
    await session.flush()

    for resp in body.responses:
        session.add(ChecklistResponse(act_id=act.id, **resp.model_dump()))

    for key in body.photo_keys:
        session.add(
            Photo(
                act_id=act.id,
                kind=PhotoKind.OTHER,
                object_key=key,
                content_type="image/jpeg",
                size_bytes=0,
                created_at=datetime.now(timezone.utc),
            )
        )

    await session.commit()
    await session.refresh(act)
    return act


@router.post("/{act_id}/submit", response_model=ActOut)
async def submit_act(
    act_id: UUID,
    body: ActSubmit,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_roles(UserRole.CONTRACTOR, UserRole.MASTER, UserRole.ADMIN)),
):
    act = await session.get(Act, act_id)
    if not act:
        raise HTTPException(404, "Акт не найден")
    if act.status not in (ActStatus.DRAFT, ActStatus.REJECTED):
        raise HTTPException(400, f"Акт в статусе {act.status.value}, нельзя подписать")

    # 1) Сохраняем ответы чек-листа
    await session.execute(
        ChecklistResponse.__table__.delete().where(ChecklistResponse.act_id == act.id)
    )
    for r in body.responses:
        session.add(ChecklistResponse(act_id=act.id, **r.model_dump()))

    # 2) Фиксируем фактическое время и гео
    act.actual_at = body.actual_at
    act.actual_latitude = body.actual_latitude
    act.actual_longitude = body.actual_longitude

    # 3) Снимок телеметрии equipment объекта
    wo = await session.get(WorkOrder, act.work_order_id)
    equipment_list = (
        await session.scalars(
            select(Equipment).where(Equipment.object_id == wo.object_id)
        )
    ).all()

    adapter = get_asutp_adapter()
    after_snapshots: dict[str, dict] = {}
    before_snapshots: dict[str, dict] = {}
    for eq in equipment_list:
        snap = await adapter.get_snapshot(eq.id, at=body.actual_at)
        after_snapshots[eq.serial_number] = snap["params"]
        if act.telemetry_before_json is None:
            # первый раз — сохраняем "до" со сдвигом 1 час назад
            before_snap = await adapter.get_snapshot(
                eq.id, at=body.actual_at.replace(hour=max(0, body.actual_at.hour - 1))
            )
            before_snapshots[eq.serial_number] = before_snap["params"]
    act.telemetry_after_json = after_snapshots
    if act.telemetry_before_json is None:
        act.telemetry_before_json = before_snapshots

    # 4) Меняем статус на submitted
    act.status = ActStatus.SUBMITTED
    wo.status = WorkOrderStatus.SUBMITTED
    await session.commit()

    # 5) Запускаем авто-проверку
    from app.services.rules import auto_check_act

    result = await auto_check_act(session, act)
    act.auto_check_passed = result.passed
    act.auto_check_score = result.score
    act.auto_check_details = result.details

    if result.passed:
        act.status = ActStatus.AUTO_CONFIRMED
        wo.status = WorkOrderStatus.AUTO_CONFIRMED
    else:
        act.status = ActStatus.DELAYED_VERIFICATION
        wo.status = WorkOrderStatus.DELAYED_VERIFICATION

    await session.commit()
    await session.refresh(act)
    return act


@router.post("/{act_id}/review", response_model=ActOut)
async def review_act(
    act_id: UUID,
    body: ActReview,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_roles(UserRole.MASTER, UserRole.TECHNOLOGIST, UserRole.MANAGER, UserRole.ADMIN)),
):
    act = await session.get(Act, act_id)
    if not act:
        raise HTTPException(404, "Акт не найден")

    wo = await session.get(WorkOrder, act.work_order_id)
    act.confirmed_by_user_id = user.id
    act.confirmed_at = datetime.now(timezone.utc)
    act.reviewer_comment = body.comment

    if body.decision == "confirm":
        act.status = ActStatus.CONFIRMED
        wo.status = WorkOrderStatus.CONFIRMED
    else:
        act.status = ActStatus.REJECTED
        wo.status = WorkOrderStatus.REJECTED
        wo.rejection_reason = body.comment

    await session.commit()
    await session.refresh(act)
    return act
