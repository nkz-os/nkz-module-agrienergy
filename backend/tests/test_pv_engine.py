"""PVEngine sanity: solar position plausibility, power bounds, thermal derating."""

from datetime import datetime, timezone

import pytest

from app.engines.pv_engine import PVEngine, PVSpec

LAT, LON = 43.3, -2.0
NOON = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
MIDNIGHT = datetime(2026, 6, 21, 0, 0, tzinfo=timezone.utc)
SPEC = PVSpec(tilt=30.0, azimuth=180.0, capacity_w=1000.0, module_area_m2=8.0)


def test_summer_noon_produces_power():
    res = PVEngine(LAT, LON).calculate_expected_power(NOON, SPEC, ghi=800, dni=700, dhi=120)
    assert res["expected_power_w"] > 100.0
    # STC scaling + temp derating can exceed nameplate slightly; bound generously
    assert res["expected_power_w"] <= SPEC.capacity_w * 1.3
    assert 45.0 < res["solar_elevation"] < 75.0  # solstice noon at lat 43.3
    assert res["poa_global"] > 0


def test_midnight_zero_power():
    res = PVEngine(LAT, LON).calculate_expected_power(MIDNIGHT, SPEC, ghi=0, dni=0, dhi=0)
    assert res["expected_power_w"] == 0.0
    assert res["solar_elevation"] < 0


def test_thermal_derating_hot_air_less_power():
    eng = PVEngine(LAT, LON)
    cool = eng.calculate_expected_power(NOON, SPEC, 800, 700, 120, temp_air=15.0)
    hot = eng.calculate_expected_power(NOON, SPEC, 800, 700, 120, temp_air=45.0)
    assert hot["expected_power_w"] < cool["expected_power_w"]


def test_power_never_negative():
    res = PVEngine(LAT, LON).calculate_expected_power(NOON, SPEC, ghi=1, dni=0, dhi=1, temp_air=80.0)
    assert res["expected_power_w"] >= 0.0


def test_solar_azimuth_south_at_noon():
    res = PVEngine(LAT, LON).calculate_expected_power(NOON, SPEC, 800, 700, 120)
    assert 150.0 < res["solar_azimuth"] < 210.0
