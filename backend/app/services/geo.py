"""Гео-утилиты: проверка попадания в радиус объекта."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import NamedTuple


class GeoResult(NamedTuple):
    distance_m: float
    in_radius: bool


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние в метрах между двумя точками (WGS84)."""
    r = 6_371_000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * r * asin(sqrt(a))


def check_geo(
    obj_lat: float | None,
    obj_lon: float | None,
    actual_lat: float | None,
    actual_lon: float | None,
    radius_m: int,
) -> GeoResult | None:
    """Возвращает None если у объекта нет геопривязки (проверка невозможна)."""
    if None in (obj_lat, obj_lon, actual_lat, actual_lon):
        return None
    assert obj_lat is not None and obj_lon is not None
    assert actual_lat is not None and actual_lon is not None
    d = haversine_m(obj_lat, obj_lon, actual_lat, actual_lon)
    return GeoResult(distance_m=d, in_radius=d <= radius_m)
