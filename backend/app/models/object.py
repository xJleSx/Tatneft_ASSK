"""Object: производственный объект (куст, скважина).

Иерархия:
- cluster (куст скважин) → well (скважина) → equipment
- Объекты — это узлы дерева, к ним привязаны наряды-заказы.
- Геолокация хранится на любом уровне (для проверки присутствия в радиусе).
"""
from __future__ import annotations

import enum
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ObjectKind(str, enum.Enum):
    CLUSTER = "cluster"  # куст
    WELL = "well"        # скважина
    FACILITY = "facility"  # прочее (насосная, КНС и т.п.)


class Object(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "objects"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    kind: Mapped[ObjectKind] = mapped_column(
        Enum(ObjectKind, name="object_kind"), nullable=False, index=True
    )

    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("objects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Геолокация (WGS84). Один узел иерархии — одна точка.
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)

    # Ответственный (мастер/технолог) со стороны Татнефти
    responsible_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    parent = relationship("Object", remote_side="Object.id", lazy="noload")
    children = relationship("Object", lazy="noload")
    equipment = relationship("Equipment", back_populates="object", lazy="noload")
    work_orders = relationship("WorkOrder", back_populates="object", lazy="noload")
