"""Act: акт выполненных работ (цифровой).

Привязан к WorkOrder. Содержит заполненные пункты чек-листа и фото.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Numeric,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ActStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    AUTO_CONFIRMED = "auto_confirmed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    DELAYED_VERIFICATION = "delayed_verification"
    VERIFIED = "verified"
    ISSUE_FOUND = "issue_found"


class Act(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "acts"

    work_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contractor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status: Mapped[ActStatus] = mapped_column(
        Enum(ActStatus, name="act_status"),
        default=ActStatus.DRAFT,
        nullable=False,
        index=True,
    )

    # Фактические гео и время (для anti-fraud)
    actual_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    actual_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    actual_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    # Снимок телеметрии equipment на момент подачи акта
    telemetry_before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    telemetry_after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Итог автопроверки
    auto_check_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    auto_check_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    auto_check_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Кто принял (мастер/технолог)
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    work_order = relationship("WorkOrder", back_populates="acts", lazy="noload")
    responses = relationship(
        "ChecklistResponse",
        back_populates="act",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    photos = relationship(
        "Photo", back_populates="act", cascade="all, delete-orphan", lazy="noload"
    )


class ChecklistResponse(UUIDPKMixin, Base):
    """Заполненный пункт чек-листа в акте.

    Поле created_at ставится при первом сохранении; updated_at не используется
    (после подписания акта ответы иммутабельны).
    """

    __tablename__ = "checklist_responses"

    act_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("acts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("checklist_steps.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Универсальный контейнер значения
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    deviation: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    act = relationship("Act", back_populates="responses", lazy="noload")
