"""Базовые тесты: geo + auth + check."""
import pytest

from app.services.geo import check_geo, haversine_m


def test_haversine_same_point_zero():
    assert haversine_m(55.0, 50.0, 55.0, 50.0) < 1.0


def test_haversine_one_degree_lat():
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert 110_000 < d < 112_000


def test_geo_check_in_radius():
    res = check_geo(55.0, 50.0, 55.0001, 50.0001, radius_m=75)
    assert res is not None
    assert res.in_radius is True


def test_geo_check_out_of_radius():
    res = check_geo(55.0, 50.0, 56.0, 50.0, radius_m=75)
    assert res is not None
    assert res.in_radius is False
    assert res.distance_m > 100_000


def test_geo_check_no_coords():
    assert check_geo(None, None, 55.0, 50.0, 75) is None
