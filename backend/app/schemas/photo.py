"""Схемы фото и телеметрии."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from app.models.photo import PhotoKind
from app.schemas.common import ORMModel


class PhotoOut(ORMModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    act_id: UUID
    kind: PhotoKind
    object_key: str
    content_type: str
    size_bytes: int
    taken_at: datetime | None
    latitude: Decimal | None
    longitude: Decimal | None
    sha256: str | None
    created_at: datetime


class PhotoUploadRequest(ORMModel):
    kind: PhotoKind
    taken_at: datetime | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    # file загружается multipart, не через JSON


class TelemetryOut(ORMModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    equipment_id: UUID
    observed_at: datetime
    params: dict[str, Any]
    source: str
