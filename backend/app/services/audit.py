"""Сервис аудита: единая точка записи в AuditLog.

Использование:
    from app.services.audit import audit
    audit(session, user_id=user.id, action="order.create", entity_type="work_order", entity_id=wo.id,
          request=request, details={"number": wo.number})

Запись добавляется в session.add(), но НЕ flush-ится и НЕ commit-ится — это
ответственность вызывающего кода (типично flush идёт перед commit в эндпоинте).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


def _client_meta(request: Request | None) -> tuple[str | None, str | None]:
    if request is None or request.client is None:
        return None, None
    ip = request.client.host
    ua = request.headers.get("user-agent")
    if ua and len(ua) > 512:
        ua = ua[:512]
    return ip, ua


def audit(
    session: AsyncSession,
    *,
    action: str,
    user_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Добавить запись в AuditLog (ещё не закоммичена — это делает вызывающий)."""
    ip, ua = _client_meta(request)
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type or "",
            entity_id=entity_id,
            details=details,
            ip_address=ip,
            user_agent=ua,
            created_at=datetime.now(UTC),
        )
    )
