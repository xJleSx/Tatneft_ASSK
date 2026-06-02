"""Equipment: оборудование на объекте (УШГН, УЭЦН, и т.п.)."""

from __future__ import annotations

import enum
from datetime import date
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class EquipmentType(str, enum.Enum):
    USHGN = "ushgn"  # штанговый насос (УШГН)
    UECN = "uecn"  # электроцентробежный насос (УЭЦН)
    WELLHEAD = "wellhead"  # устьевая арматура
    PUMP_UNIT = "pump_unit"
    SEPARATOR = "separator"
    OTHER = "other"


class Equipment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "equipment"

    object_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("objects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[EquipmentType] = mapped_column(
        Enum(EquipmentType, name="equipment_type"),
        nullable=False,
        index=True,
    )
    serial_number: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commissioned_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Произвольные номинальные параметры (JSON-строка, чтобы не плодить колонки)
    # Например: {"P_nom": 50, "Q_nom": 80, "I_nom": 45}
    nominal_params_json: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    object = relationship("Object", back_populates="equipment", lazy="noload")
    telemetry = relationship("TelemetryReading", back_populates="equipment", lazy="noload")
