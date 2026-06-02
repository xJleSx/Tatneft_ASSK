"""WorkOrder: наряд-заказ (заявка) на выполнение работ.

Жизненный цикл:
draft → assigned → in_progress → submitted (акт подан) → confirmed | rejected
                                       → delayed_verification → verified | issue
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class WorkOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    AUTO_CONFIRMED = "auto_confirmed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    DELAYED_VERIFICATION = "delayed_verification"
    VERIFIED = "verified"
    ISSUE_FOUND = "issue_found"
    CANCELLED = "cancelled"


class WorkOrderPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class WorkOrder(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "work_orders"

    number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    object_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("objects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    work_type_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_types.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    contractor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contractors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[WorkOrderStatus] = mapped_column(
        Enum(WorkOrderStatus, name="work_order_status"),
        default=WorkOrderStatus.DRAFT,
        nullable=False,
        index=True,
    )

    priority: Mapped[WorkOrderPriority] = mapped_column(
        Enum(
            WorkOrderPriority,
            name="work_order_priority",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=WorkOrderPriority.NORMAL,
        nullable=False,
        index=True,
    )

    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Плановая стоимость / факт (для отчётов и рейтинга)
    planned_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Номер заявки/дефекта из внешней системы (1С, SAP)
    defect_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # True, если наряд — только диагностика, тип работ уточняется по результатам
    is_diagnostic: Mapped[bool] = mapped_column(default=False, nullable=False)

    object = relationship("Object", back_populates="work_orders", lazy="noload")
    work_type = relationship("WorkType", back_populates="work_orders", lazy="noload")
    contractor = relationship("Contractor", back_populates="work_orders", lazy="noload")
    acts = relationship("Act", back_populates="work_order", lazy="noload")
