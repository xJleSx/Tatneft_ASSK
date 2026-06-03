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


# Разрешённые переходы WorkOrderStatus. Используется для валидации в API/сервисах,
# чтобы нельзя было «прыгнуть» через состояния.
WORK_ORDER_TRANSITIONS: dict[WorkOrderStatus, frozenset[WorkOrderStatus]] = {
    WorkOrderStatus.DRAFT: frozenset(
        {WorkOrderStatus.ASSIGNED, WorkOrderStatus.CANCELLED}
    ),
    WorkOrderStatus.ASSIGNED: frozenset(
        {WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELLED}
    ),
    WorkOrderStatus.IN_PROGRESS: frozenset(
        {
            WorkOrderStatus.SUBMITTED,
            WorkOrderStatus.AUTO_CONFIRMED,
            WorkOrderStatus.DELAYED_VERIFICATION,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.SUBMITTED: frozenset(
        {
            WorkOrderStatus.AUTO_CONFIRMED,
            WorkOrderStatus.DELAYED_VERIFICATION,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.AUTO_CONFIRMED: frozenset(
        {
            WorkOrderStatus.CONFIRMED,
            WorkOrderStatus.ISSUE_FOUND,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.DELAYED_VERIFICATION: frozenset(
        {WorkOrderStatus.VERIFIED, WorkOrderStatus.ISSUE_FOUND}
    ),
    WorkOrderStatus.CONFIRMED: frozenset(),
    WorkOrderStatus.VERIFIED: frozenset(),
    WorkOrderStatus.ISSUE_FOUND: frozenset(
        {WorkOrderStatus.ASSIGNED, WorkOrderStatus.CANCELLED}
    ),
    WorkOrderStatus.REJECTED: frozenset(
        {WorkOrderStatus.DRAFT, WorkOrderStatus.CANCELLED}
    ),
    WorkOrderStatus.CANCELLED: frozenset(),
}


def can_transition(from_status: WorkOrderStatus, to_status: WorkOrderStatus) -> bool:
    """Можно ли перевести наряд из from_status в to_status."""
    if from_status == to_status:
        return True  # no-op
    return to_status in WORK_ORDER_TRANSITIONS.get(from_status, frozenset())


def assert_transition(from_status: WorkOrderStatus, to_status: WorkOrderStatus) -> None:
    """Бросает ValueError при недопустимом переходе WorkOrder."""
    if not can_transition(from_status, to_status):
        raise ValueError(
            f"Недопустимый переход WorkOrder: {from_status.value} -> {to_status.value}"
        )


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
