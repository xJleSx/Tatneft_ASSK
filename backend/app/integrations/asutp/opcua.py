"""Stub для будущей интеграции по OPC-UA (реальная АСУ ТП).

Будет использовать asyncua или opcua-asyncio. Пока — NotImplementedError.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.integrations.asutp.base import AsutpAdapter


class OpcUaAdapter(AsutpAdapter):
    def __init__(self, endpoint_url: str) -> None:
        self.endpoint_url = endpoint_url

    async def get_snapshot(
        self, equipment_id: UUID, at: datetime | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError("OPC-UA адаптер будет реализован после доступа к АСУ ТП")

    async def get_history(
        self, equipment_id: UUID, since: datetime, until: datetime
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("OPC-UA адаптер будет реализован после доступа к АСУ ТП")
