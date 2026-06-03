"""Acts: цифровые акты выполненных работ."""

from __future__ import annotations

import hashlib
import json
import os
import secrets as _secrets
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_session
from app.integrations.asutp.factory import get_asutp_adapter
from app.models.act import Act, ActStatus, ChecklistResponse, assert_act_transition
from app.models.equipment import Equipment
from app.models.order import WorkOrder, WorkOrderStatus, assert_transition
from app.models.photo import Photo, PhotoKind
from app.models.user import User, UserRole
from app.schemas.order import ActCreate, ActOut, ActReview, ActSubmit
from app.services.audit import audit

router = APIRouter(prefix="/acts", tags=["acts"])


@router.get("/", response_model=list[ActOut])
async def list_acts(
    work_order_id: UUID | None = None,
    status: ActStatus | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[Act]:
    q = select(Act).order_by(Act.created_at.desc()).limit(limit)
    if work_order_id:
        q = q.where(Act.work_order_id == work_order_id)
    if status:
        q = q.where(Act.status == status)
    if user.role == UserRole.CONTRACTOR:
        q = q.where(Act.contractor_user_id == user.id)
    return list((await session.scalars(q)).all())


@router.get("/{act_id}", response_model=dict)
async def get_act_detail(
    act_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Акт целиком: сам акт + ответы чек-листа + фото + наряд."""
    act = await session.get(Act, act_id)
    if not act:
        raise HTTPException(404, "Акт не найден")
    if user.role == UserRole.CONTRACTOR and act.contractor_user_id != user.id:
        raise HTTPException(403, "Чужой акт")

    responses = (
        await session.scalars(select(ChecklistResponse).where(ChecklistResponse.act_id == act_id))
    ).all()
    photos = (
        await session.scalars(
            select(Photo).where(Photo.act_id == act_id).order_by(Photo.created_at)
        )
    ).all()
    wo = await session.get(WorkOrder, act.work_order_id)

    return {
        "id": str(act.id),
        "work_order_id": str(act.work_order_id),
        "status": act.status.value,
        "actual_at": act.actual_at.isoformat() if act.actual_at else None,
        "actual_latitude": str(act.actual_latitude) if act.actual_latitude is not None else None,
        "actual_longitude": str(act.actual_longitude) if act.actual_longitude is not None else None,
        "auto_check_passed": act.auto_check_passed,
        "auto_check_score": act.auto_check_score,
        "auto_check_details": act.auto_check_details,
        "telemetry_before": act.telemetry_before_json,
        "telemetry_after": act.telemetry_after_json,
        "reviewer_comment": act.reviewer_comment,
        "confirmed_at": act.confirmed_at.isoformat() if act.confirmed_at else None,
        "created_at": act.created_at.isoformat(),
        "responses": [
            {
                "id": str(r.id),
                "step_id": str(r.step_id),
                "value_bool": r.value_bool,
                "value_numeric": str(r.value_numeric) if r.value_numeric is not None else None,
                "value_text": r.value_text,
                "value_json": r.value_json,
                "passed": r.passed,
                "comment": r.comment,
            }
            for r in responses
        ],
        "photos": [
            {
                "id": str(p.id),
                "kind": p.kind.value,
                "object_key": p.object_key,
                "url": f"/api/v1/acts/photos/{p.id}",
                "content_type": p.content_type,
                "size_bytes": p.size_bytes,
                "taken_at": p.taken_at.isoformat() if p.taken_at else None,
                "latitude": str(p.latitude) if p.latitude is not None else None,
                "longitude": str(p.longitude) if p.longitude is not None else None,
                "has_exif_gps": p.latitude is not None and p.longitude is not None,
            }
            for p in photos
        ],
        "work_order": (
            {
                "id": str(wo.id),
                "number": wo.number,
                "status": wo.status.value,
                "object_id": str(wo.object_id),
                "contractor_id": str(wo.contractor_id) if wo.contractor_id else None,
            }
            if wo
            else None
        ),
    }


@router.post("/", response_model=ActOut, status_code=201)
async def create_draft_act(
    body: ActCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_roles(UserRole.CONTRACTOR, UserRole.MASTER, UserRole.ADMIN)),
) -> Act:
    wo = await session.get(WorkOrder, body.work_order_id)
    if not wo:
        raise HTTPException(404, "Наряд-заказ не найден")
    act = Act(
        work_order_id=body.work_order_id,
        contractor_user_id=user.id,
        status=ActStatus.DRAFT,
        actual_latitude=body.actual_latitude,
        actual_longitude=body.actual_longitude,
        actual_at=body.actual_at or datetime.now(UTC),
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
                created_at=datetime.now(UTC),
            )
        )

    audit(
        session,
        action="act.create",
        user_id=user.id,
        entity_type="act",
        entity_id=act.id,
        request=request,
        details={
            "work_order_id": str(wo.id),
            "responses": len(body.responses),
            "photo_keys": len(body.photo_keys),
        },
    )
    await session.commit()
    await session.refresh(act)
    return act


@router.post("/{act_id}/submit", response_model=ActOut)
async def submit_act(
    act_id: UUID,
    body: ActSubmit,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_roles(UserRole.CONTRACTOR, UserRole.MASTER, UserRole.ADMIN)),
) -> Act:
    act = await session.get(Act, act_id)
    if not act:
        raise HTTPException(404, "Акт не найден")
    try:
        assert_act_transition(act.status, ActStatus.SUBMITTED)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    # 1) Сохраняем ответы чек-листа
    await session.execute(delete(ChecklistResponse).where(ChecklistResponse.act_id == act.id))
    for r in body.responses:
        session.add(ChecklistResponse(act_id=act.id, **r.model_dump()))

    # 2) Фиксируем фактическое время и гео
    act.actual_at = body.actual_at
    act.actual_latitude = body.actual_latitude
    act.actual_longitude = body.actual_longitude

    # 3) Снимок телеметрии equipment объекта
    wo = await session.get(WorkOrder, act.work_order_id)
    if wo is None:
        raise HTTPException(404, "Наряд-заказ не найден")
    equipment_list = (
        await session.scalars(select(Equipment).where(Equipment.object_id == wo.object_id))
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
    assert_transition(wo.status, WorkOrderStatus.SUBMITTED)
    wo.status = WorkOrderStatus.SUBMITTED

    audit(
        session,
        action="act.submit",
        user_id=user.id,
        entity_type="act",
        entity_id=act.id,
        request=request,
        details={
            "work_order_id": str(wo.id),
            "responses": len(body.responses),
            "auto_check_pending": True,
        },
    )
    await session.commit()

    # 5) Запускаем авто-проверку
    from app.services.rules import auto_check_act

    result = await auto_check_act(session, act, work_order=wo)
    act.auto_check_passed = result.passed
    act.auto_check_score = result.score
    act.auto_check_details = result.details

    if result.passed:
        act.status = ActStatus.AUTO_CONFIRMED
        assert_transition(wo.status, WorkOrderStatus.AUTO_CONFIRMED)
        wo.status = WorkOrderStatus.AUTO_CONFIRMED
    else:
        act.status = ActStatus.DELAYED_VERIFICATION
        assert_transition(wo.status, WorkOrderStatus.DELAYED_VERIFICATION)
        wo.status = WorkOrderStatus.DELAYED_VERIFICATION

    audit(
        session,
        action="act.auto_check",
        user_id=user.id,
        entity_type="act",
        entity_id=act.id,
        request=request,
        details={
            "work_order_id": str(wo.id),
            "passed": result.passed,
            "score": result.score,
            "final_status": act.status.value,
            "work_order_status": wo.status.value,
        },
    )
    await session.commit()
    await session.refresh(act)
    return act


# --- Фотофиксация ---

PHOTOS_DIR = Path(__file__).resolve().parent.parent.parent / "photos_storage"
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


def _exif_gps_and_dt(raw: bytes) -> tuple[dict | None, datetime | None]:
    """Извлечь GPS и время съёмки из EXIF JPEG. Возвращает (gps_dict, taken_at)."""
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        exif: Any = img.getexif() or {}
    except Exception:
        return None, None

    if not exif:
        return None, None

    # datetime
    taken_at = None
    dt_str = exif.get(36867) or exif.get(306)  # DateTimeOriginal, DateTime
    if dt_str and isinstance(dt_str, str):
        with suppress(ValueError):
            taken_at = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S").replace(tzinfo=UTC)

    # GPS
    gps_info = exif.get(34853)
    if not gps_info:
        return None, taken_at

    def _to_float(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, tuple) and len(v) == 3:
            d, m, s = v
            return float(d) + float(m) / 60.0 + float(s) / 3600.0
        try:
            return float(v[0]) / float(v[1]) if len(v) == 2 else float(v)
        except Exception:
            return None

    lat = _to_float(gps_info.get(2))
    lat_ref = gps_info.get(1)
    lon = _to_float(gps_info.get(4))
    lon_ref = gps_info.get(3)
    if lat is not None and lat_ref in (b"S", "S"):
        lat = -lat
    if lon is not None and lon_ref in (b"W", "W"):
        lon = -lon

    if lat is None or lon is None:
        return None, taken_at

    return {"lat": lat, "lon": lon}, taken_at


@router.post("/{act_id}/photos")
async def upload_photo(
    act_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("other"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Загрузка фото к акту. Извлекает EXIF GPS и время съёмки (anti-fraud)."""
    act = await session.get(Act, act_id)
    if not act:
        raise HTTPException(404, "Акт не найден")
    if user.role == UserRole.CONTRACTOR and act.contractor_user_id != user.id:
        raise HTTPException(403, "Чужой акт")

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Пустой файл")
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(413, "Файл больше 15 МБ")

    photo_kind = kind if kind in {k.value for k in PhotoKind} else "other"

    ext = (file.filename or "img.jpg").rsplit(".", 1)[-1].lower() or "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    fname = f"{act_id}_{_secrets.token_hex(6)}.{ext}"
    fpath = PHOTOS_DIR / fname
    fpath.write_bytes(raw)

    sha = hashlib.sha256(raw).hexdigest()
    gps, taken_at = _exif_gps_and_dt(raw)

    photo = Photo(
        act_id=act_id,
        kind=PhotoKind(photo_kind),
        object_key=str(fpath),
        content_type=file.content_type or "image/jpeg",
        size_bytes=len(raw),
        taken_at=taken_at,
        latitude=gps["lat"] if gps else None,
        longitude=gps["lon"] if gps else None,
        sha256=sha,
        exif_json=json.dumps(
            {"source_filename": file.filename, "has_exif": gps is not None}, ensure_ascii=False
        ),
        created_at=datetime.now(UTC),
    )
    session.add(photo)
    await session.flush()
    audit(
        session,
        action="act.photo_upload",
        user_id=user.id,
        entity_type="photo",
        entity_id=photo.id,
        request=request,
        details={
            "act_id": str(act_id),
            "kind": photo_kind,
            "size_bytes": len(raw),
            "has_exif_gps": gps is not None,
            "sha256": sha,
        },
    )
    await session.commit()
    await session.refresh(photo)

    return {
        "id": str(photo.id),
        "kind": photo.kind.value,
        "size_bytes": photo.size_bytes,
        "url": f"/api/v1/acts/photos/{photo.id}",
        "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
        "latitude": str(photo.latitude) if photo.latitude is not None else None,
        "longitude": str(photo.longitude) if photo.longitude is not None else None,
        "has_exif_gps": photo.latitude is not None and photo.longitude is not None,
    }


@router.get("/photos/{photo_id}")
async def get_photo(
    photo_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """Отдать бинарь фото (для отображения в UI)."""
    photo = await session.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404, "Фото не найдено")
    if not os.path.exists(photo.object_key):
        raise HTTPException(404, "Файл потерян")
    return FileResponse(photo.object_key, media_type=photo.content_type)


@router.post("/{act_id}/review", response_model=ActOut)
async def review_act(
    act_id: UUID,
    body: ActReview,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_roles(UserRole.MASTER, UserRole.TECHNOLOGIST, UserRole.MANAGER, UserRole.ADMIN)
    ),
) -> Act:
    act = await session.get(Act, act_id)
    if not act:
        raise HTTPException(404, "Акт не найден")

    wo = await session.get(WorkOrder, act.work_order_id)
    if wo is None:
        raise HTTPException(404, "Наряд-заказ не найден")
    act.confirmed_by_user_id = user.id
    act.confirmed_at = datetime.now(UTC)
    act.reviewer_comment = body.comment

    if body.decision == "confirm":
        target_act = ActStatus.CONFIRMED
        target_wo = WorkOrderStatus.CONFIRMED
    else:
        target_act = ActStatus.REJECTED
        target_wo = WorkOrderStatus.REJECTED
    try:
        assert_act_transition(act.status, target_act)
        assert_transition(wo.status, target_wo)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    act.status = target_act
    wo.status = target_wo
    if body.decision == "reject":
        wo.rejection_reason = body.comment

    audit(
        session,
        action=f"act.review.{body.decision}",
        user_id=user.id,
        entity_type="act",
        entity_id=act.id,
        request=request,
        details={
            "work_order_id": str(wo.id),
            "from_act_status": ActStatus.AUTO_CONFIRMED.value
            if act.status == target_act and body.decision == "confirm"
            else ActStatus.DELAYED_VERIFICATION.value,
            "to_act_status": target_act.value,
            "to_work_order_status": target_wo.value,
            "comment": body.comment,
        },
    )
    await session.commit()
    await session.refresh(act)
    return act
