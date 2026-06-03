"""Кросс-диалектные типы для полей, у которых нет нативной поддержки в SQLite.

Основная БД — PostgreSQL/TimescaleDB, в проде используется JSONB.
Для тестов на SQLite нужен фолбэк, иначе DDL не скомпилируется.
"""
from __future__ import annotations

from sqlalchemy import JSON, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB


class JSONBCompat(TypeDecorator):
    """JSONB на PostgreSQL, обычный JSON на остальных диалектах (SQLite — тесты)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())
