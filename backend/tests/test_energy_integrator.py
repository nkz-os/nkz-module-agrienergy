"""Trapezoidal Wh integration tests."""

from app.services.energy_integrator import trapezoidal_wh


def test_trapezoidal_two_hour_constant_power():
    points = [
        {"ts": "2026-06-25T10:00:00Z", "value": 1000.0},
        {"ts": "2026-06-25T12:00:00Z", "value": 1000.0},
    ]
    assert trapezoidal_wh(points) == 2000.0


def test_trapezoidal_ramp():
    points = [
        {"ts": "2026-06-25T00:00:00Z", "value": 0.0},
        {"ts": "2026-06-25T01:00:00Z", "value": 200.0},
    ]
    assert trapezoidal_wh(points) == 100.0


def test_trapezoidal_clamps_negative_power():
    points = [
        {"ts": "2026-06-25T00:00:00Z", "value": -500.0},
        {"ts": "2026-06-25T01:00:00Z", "value": 100.0},
    ]
    assert trapezoidal_wh(points) == 50.0


def test_trapezoidal_insufficient_points():
    assert trapezoidal_wh([]) == 0.0
    assert trapezoidal_wh([{"ts": "2026-06-25T00:00:00Z", "value": 100.0}]) == 0.0
