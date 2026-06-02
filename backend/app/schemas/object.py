"""Схемы производственных объектов и оборудования."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import ConfigDict, Field

from app.models.equipment import EquipmentType
from app.models.object import ObjectKind
from app.schemas.common import ORMModel


class ObjectBase(ORMModel):
    name: str
    code: str
    kind: ObjectKind
    parent_id: UUID | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    responsible_user_id: UUID | None = None


class ObjectCreate(ObjectBase):
    pass


class ObjectUpdate(ORMModel):
    name: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    responsible_user_id: UUID | None = None


class ObjectOut(ObjectBase):
    id: UUID
    created_at: datetime


class EquipmentBase(ORMModel):
    object_id: UUID
    type: EquipmentType
    serial_number: str
    manufacturer: str | None = None
    model: str | None = None
    commissioned_at: date | None = None
    nominal_params_json: str | None = None


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentOut(EquipmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
