"""ContractorRating: агрегированный рейтинг подрядчика за период."""

from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class RatingPeriod(str, enum.Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class ContractorRating(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "contractor_ratings"

    contractor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contractors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period: Mapped[RatingPeriod] = mapped_column(
        Enum(RatingPeriod, name="rating_period"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    orders_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_auto_confirmed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repeat_visits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Суб-скоры
    completeness_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), nullable=False
    )
    timeliness_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), nullable=False
    )
    quality_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), nullable=False
    )
    total_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), nullable=False
    )

    # Использованные веса
    weights_json: Mapped[str | None] = mapped_column(String(512), nullable=True)

    contractor = relationship("Contractor", back_populates="ratings", lazy="noload")
