"""Схемы типов работ и чек-листов."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from app.models.work import StepDataType, WorkCategory
from app.schemas.common import ORMModel


class WorkTypeBase(ORMModel):
    code: str
    name: str
    category: WorkCategory
    planned_duration_hours: Decimal | None = None
    applies_to_equipment_type: str | None = None
    description: str | None = None


class WorkTypeCreate(WorkTypeBase):
    pass


class WorkTypeOut(WorkTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class ChecklistStepBase(ORMModel):
    order_index: int
    title: str
    description: str | None = None
    data_type: StepDataType
    is_required: bool = True
    norm_json: dict[str, Any] | None = None
    telemetry_param: str | None = None


class ChecklistStepCreate(ChecklistStepBase):
    pass


class ChecklistStepOut(ChecklistStepBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class ChecklistTemplateBase(ORMModel):
    work_type_id: UUID
    version: int = 1
    is_active: bool = True


class ChecklistTemplateCreate(ChecklistTemplateBase):
    steps: list[ChecklistStepCreate] = Field(default_factory=list)


class ChecklistTemplateOut(ChecklistTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    steps: list[ChecklistStepOut] = []
