"""Work: типы работ и шаблоны чек-листов.

Тип работ (WorkType) — например, "ТР-1" (текущий ремонт скважины №1),
"Замена УЭЦН", "ТО-2" (техническое обслуживание).

К каждому WorkType привязан ChecklistTemplate с шагами ChecklistStep.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class WorkCategory(str, enum.Enum):
    WORKOVER = "workover"  # текущий ремонт (ТР)
    OVERHAUL = "overhaul"  # капитальный ремонт (КР)
    ROUTINE = "routine"  # ТО, регламентные работы
    EMERGENCY = "emergency"  # аварийные
    INSTALLATION = "installation"  # монтаж/замена


class StepDataType(str, enum.Enum):
    BOOLEAN = "boolean"  # да/нет
    NUMERIC = "numeric"  # число (с допуском)
    TEXT = "text"  # свободный комментарий
    PHOTO = "photo"  # требуется фото
    CHOICE = "choice"  # выбор из вариантов


class WorkType(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "work_types"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[WorkCategory] = mapped_column(
        Enum(WorkCategory, name="work_category"), nullable=False, index=True
    )

    # Плановые длительность и трудоёмкость
    planned_duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

    # Применимо к какому типу оборудования (если None — для всех)
    applies_to_equipment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    template = relationship(
        "ChecklistTemplate",
        back_populates="work_type",
        uselist=False,
        lazy="noload",
    )
    work_orders = relationship("WorkOrder", back_populates="work_type", lazy="noload")


class ChecklistTemplate(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "checklist_templates"

    work_type_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_types.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    work_type = relationship("WorkType", back_populates="template", lazy="noload")
    steps = relationship(
        "ChecklistStep",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="ChecklistStep.order_index",
        lazy="noload",
    )


class ChecklistStep(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "checklist_steps"

    template_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("checklist_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[StepDataType] = mapped_column(
        Enum(StepDataType, name="step_data_type"), nullable=False
    )
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Нормативы: для numeric — {"nominal": 50, "min": 45, "max": 55, "unit": "атм"}
    #             для choice — {"options": ["вариант1", "вариант2"]}
    norm_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Параметр АСУ ТП, который нужно сравнить (например, "P_buf")
    telemetry_param: Mapped[str | None] = mapped_column(String(64), nullable=True)

    template = relationship("ChecklistTemplate", back_populates="steps", lazy="noload")
