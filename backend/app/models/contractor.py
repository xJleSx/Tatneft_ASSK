"""Contractor: подрядная организация."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Contractor(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "contractors"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    inn: Mapped[str] = mapped_column(String(12), unique=True, index=True, nullable=False)
    kpp: Mapped[str | None] = mapped_column(String(9), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Какие типы работ выполняет (для матчинга)
    specializations: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Текущий агрегированный рейтинг (денормализованно для быстрого отображения)
    rating_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), nullable=False
    )

    users = relationship("User", back_populates="contractor", lazy="noload")
    work_orders = relationship("WorkOrder", back_populates="contractor", lazy="noload")
    ratings = relationship("ContractorRating", back_populates="contractor", lazy="noload")
