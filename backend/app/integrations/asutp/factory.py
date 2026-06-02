"""Фабрика адаптеров АСУ ТП по настройке ASUTP_MODE."""

from __future__ import annotations

from app.core.config import settings
from app.integrations.asutp.base import AsutpAdapter
from app.integrations.asutp.mock import mock_adapter


def get_asutp_adapter() -> AsutpAdapter:
    if settings.asutp_mode == "mock":
        return mock_adapter
    if settings.asutp_mode == "opcua":
        # endpoint из переменной окружения ASUTP_OPCUA_URL
        import os

        from app.integrations.asutp.opcua import OpcUaAdapter

        url = os.getenv("ASUTP_OPCUA_URL", "opc.tcp://localhost:4840")
        return OpcUaAdapter(url)
    raise RuntimeError(f"Unknown ASUTP_MODE: {settings.asutp_mode}")
