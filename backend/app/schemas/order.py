"""Схемы нарядов-заказов и актов."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from app.models.act import ActStatus
from app.models.order import WorkOrderPriority, WorkOrderStatus
from app.schemas.common import ORMModel


class WorkOrderBase(ORMModel):
    object_id: UUID
    work_type_id: UUID | None = None
    contractor_id: UUID | None = None
    priority: WorkOrderPriority = WorkOrderPriority.NORMAL
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    planned_cost: Decimal | None = None
    description: str | None = None
    defect_ref: str | None = None
    is_diagnostic: bool = False


class WorkOrderCreate(WorkOrderBase):
    number: str | None = None  # автогенерация


class WorkOrderUpdate(ORMModel):
    contractor_id: UUID | None = None
    work_type_id: UUID | None = None
    status: WorkOrderStatus | None = None
    priority: WorkOrderPriority | None = None
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    actual_start_at: datetime | None = None
    actual_end_at: datetime | None = None
    planned_cost: Decimal | None = None
    actual_cost: Decimal | None = None
    description: str | None = None
    rejection_reason: str | None = None
    defect_ref: str | None = None
    is_diagnostic: bool | None = None


class WorkOrderOut(WorkOrderBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: str
    status: WorkOrderStatus
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    actual_cost: Decimal | None
    created_at: datetime


# --- Act ---

class ChecklistResponseIn(ORMModel):
    step_id: UUID
    value_bool: bool | None = None
    value_numeric: Decimal | None = None
    value_text: str | None = None
    value_json: dict[str, Any] | None = None
    passed: bool | None = None
    comment: str | None = None


class ChecklistResponseOut(ChecklistResponseIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class ActBase(ORMModel):
    work_order_id: UUID
    actual_latitude: Decimal | None = None
    actual_longitude: Decimal | None = None
    actual_at: datetime | None = None


class ActCreate(ActBase):
    responses: list[ChecklistResponseIn] = Field(default_factory=list)
    photo_keys: list[str] = Field(default_factory=list)  # уже загруженные в MinIO


class ActSubmit(ORMModel):
    """Подтверждение от подрядчика: акт переходит SUBMITTED → auto-check."""

    actual_latitude: Decimal
    actual_longitude: Decimal
    actual_at: datetime
    responses: list[ChecklistResponseIn] = Field(default_factory=list)


class ActReview(ORMModel):
    """Действие мастера/технолога."""

    decision: str = Field(pattern="^(confirm|reject)$")
    comment: str | None = None


class ActOut(ActBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contractor_user_id: UUID
    status: ActStatus
    auto_check_passed: bool | None
    auto_check_score: float | None
    auto_check_details: dict | None
    confirmed_by_user_id: UUID | None
    confirmed_at: datetime | None
    reviewer_comment: str | None
    created_at: datetime
