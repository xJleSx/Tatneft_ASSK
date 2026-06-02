"""Photo: фотофиксация к акту (до/после/проблема)."""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin


class PhotoKind(str, enum.Enum):
    BEFORE = "before"
    AFTER = "after"
    ISSUE = "issue"
    OTHER = "other"


class Photo(UUIDPKMixin, Base):
    __tablename__ = "photos"

    act_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("acts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[PhotoKind] = mapped_column(
        Enum(PhotoKind, name="photo_kind"), nullable=False, index=True
    )

    # MinIO / S3 ключ
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    # Гео и время (для anti-fraud)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    # Хеш содержимого (для дедупликации / проверки целостности)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # EXIF метаданные (JSON как строка для простоты)
    exif_json: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    act = relationship("Act", back_populates="photos", lazy="noload")
