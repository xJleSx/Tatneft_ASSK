"""TelemetryReading: снимок телеметрии оборудования.

Хранится в TimescaleDB hypertable (см. миграцию).
Параметры зависят от типа оборудования (УШГН/УЭЦН) — кладём в JSONB.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin
from app.db.types import JSONBCompat


class TelemetryKind(str, enum.Enum):
    SCRAPE = "scrape"  # периодический опрос
    EVENT = "event"  # событие (аларм, отключение)
    SNAPSHOT = "snapshot"  # снимок по запросу


class TelemetryReading(UUIDPKMixin, Base):
    __tablename__ = "telemetry_readings"

    equipment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("equipment.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    kind: Mapped[TelemetryKind] = mapped_column(
        Enum(TelemetryKind, name="telemetry_kind"),
        default=TelemetryKind.SCRAPE,
        nullable=False,
    )

    # Произвольный набор параметров: {"P_buf": 12.3, "Q_liq": 80, "I": 45, ...}
    params: Mapped[dict] = mapped_column(JSONBCompat, nullable=False)

    # Источник: имя адаптера/системы
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="mock")

    equipment = relationship("Equipment", back_populates="telemetry", lazy="noload")

    __table_args__ = (
        Index(
            "ix_telemetry_equipment_observed",
            "equipment_id",
            "observed_at",
        ),
    )
